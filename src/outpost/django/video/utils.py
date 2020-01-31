import io
import json
import logging
import math
import re
import subprocess
from functools import partial, reduce
from math import ceil

import boto3
import requests
from dateutil.relativedelta import relativedelta
from django.utils.translation import gettext_lazy as _
from more_itertools import chunked, divide, split_after
from webvtt import Caption, WebVTT

from .conf import settings

logger = logging.getLogger(__name__)


class FFMPEGProgressHandler:
    duration = None
    current = 0
    re_duration = re.compile("Duration: (\d{2}):(\d{2}):(\d{2}).(\d{2})[^\d]*", re.U)
    re_position = re.compile("time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})\d*", re.U | re.I)

    def __init__(self, func):
        self.func = func

    def __call__(self, line):
        def time2sec(search):
            return sum([i ** (2 - i) * int(search.group(i + 1)) for i in range(3)])

        if self.duration is None:
            duration_match = self.re_duration.match(line)
            if duration_match:
                self.duration = time2sec(duration_match)
        else:
            position_match = self.re_position.search(line)
            if position_match:
                new = time2sec(position_match)
                if new > self.current:
                    if callable(self.func):
                        self.func(new, self.duration)
                    self.current = new


class FFMPEGCropHandler:

    pattern = re.compile(
        r"^\[Parsed_cropdetect_\d+ @ 0x[0-9a-f]+\].* crop=(\d+)\:(\d+)\:(\d+)\:(\d+)$"
    )

    def __init__(self):
        self.dims = list()

    def __call__(self, line):
        matches = self.pattern.match(line)
        if not matches:
            return
        self.dims.append(map(int, matches.groups()))

    def crop(self):
        # TODO: Use minimum instead of average pixels to avoid cropping too
        # much.
        return tuple(map(lambda y: int(sum(y) / len(y)), zip(*self.dims)))


class FFMPEGVolumeLevelHandler:

    pattern = re.compile(
        r"^\[Parsed_volumedetect_\d+ @ 0x[0-9a-f]+\].* ([\w\d\_]+): (.*?)(?: dB)?$"
    )

    def __init__(self):
        self.values = dict()

    def __call__(self, line):
        matches = self.pattern.match(line)
        if not matches:
            return
        key, value = matches.groups()
        self.values[key] = value


class MP4BoxProgressHandler:
    pattern = re.compile(r"^([\w ]+): \|\s+\| \((\d+)\/(\d+)\)$")

    def __init__(self, func):
        self.func = func

    def __call__(self, line):
        matches = self.pattern.match(line)
        if not matches:
            return
        if callable(self.func):
            self.func(*m.groups())


class FFProbeProcess:
    def __init__(self, *commands, timeout=None):

        args = []
        if timeout:
            args.extend(["timeout", str(timeout)])

        args.extend(["ffprobe", "-print_format", "json"])
        args.extend(list(commands))
        logger.debug("Preparing: {}".format(" ".join(args)))
        self.cmd = partial(
            subprocess.run, args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )

    def run(self):
        probe = self.cmd()
        info = probe.stdout.decode("utf-8")
        logger.debug("Extracted metadata: {}".format(info))
        return json.loads(info)


class TranscribeException(Exception):
    pass


class TranscribeMixin:
    aws = boto3.Session(
        aws_access_key_id=settings.BASE_AWS_ACCESS_KEY,
        aws_secret_access_key=settings.BASE_AWS_SECRET_ACCESS_KEY,
        region_name=settings.BASE_AWS_REGION_NAME,
    )

    def transcribe(self, job, audio, language):
        logger.debug(f"Transcribing audio: {audio}")
        s3 = self.aws.resource("s3")
        bucket = s3.Bucket(settings.VIDEO_TRANSCRIBE_BUCKET)
        bucket.upload_file(audio, job)
        transcribe = self.aws.client("transcribe")
        transcribe.start_transcription_job(
            TranscriptionJobName=job,
            LanguageCode=language,
            MediaFormat="flac",
            Media={
                "MediaFileUri": f"https://{bucket.name}.s3.{self.aws.region_name}.amazonaws.com/{job}"
            },
        )
        return job

    def retrieve(self, job):
        logger.debug(f"Fetching transcription result for {job}")
        transcribe = self.aws.client("transcribe")
        try:
            result = transcribe.get_transcription_job(TranscriptionJobName=job).get(
                "TranscriptionJob"
            )
        except Exception as e:
            logger.error(f"Could not fetch transcription job: {e}")
            raise TranscribeException(_("Could not fetch transcription job"))
        status = result.get("TranscriptionJobStatus")
        if status != "COMPLETED":
            logger.debug(f"Job not yet completed: {job}")
            raise TranscribeException(_("Job not yet completed"))
        url = result.get("Transcript").get("TranscriptFileUri")
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Could not fetch transcription results for {job}: {e}")
            raise TranscribeException(_("Could not fetch transcription results"))
        s3 = self.aws.client("s3")
        logger.debug(f"Removing audio file from S3 bucket")
        s3.delete_object(Bucket=settings.VIDEO_TRANSCRIBE_BUCKET, Key=f"{job}.flac")
        logger.debug(f"Removing transcription job")
        transcribe.delete_transcription_job(TranscriptionJobName=job)
        return (
            result.get("CreationTime"),
            result.get("CompletionTime"),
            response.json(),
        )


def json2vtt(data):
    def timestamp(sec: float) -> str:
        t = relativedelta(microseconds=int(sec * (10 ** 6)))
        return f"{t.hours:03.0f}:{t.minutes:02.0f}:{t.seconds:02.0f}.{t.microseconds/1000:03.0f}"

    def content(a, v) -> str:
        c = max(v.get("alternatives"), key=lambda k: float(k.get("confidence"))).get(
            "content"
        )
        if not a:
            return c
        if v.get("type") == "punctuation":
            return f"{a}{c}"
        return f"{a} {c}"

    sentences = split_after(data, lambda i: i.get("type") == "punctuation")
    vtt = WebVTT()
    for s in sentences:
        csize = ceil(len(s) / 12)
        for p in divide(csize, s):
            lst = list(p)
            text = reduce(content, lst, None)
            pro = list(filter(lambda i: i.get("type") == "pronunciation", lst))
            start = timestamp(min(map(lambda i: float(i.get("start_time")), pro)))
            end = timestamp(max(map(lambda i: float(i.get("end_time")), pro)))
            caption = Caption(start, end, map(" ".join, divide(2, text.split())))
            vtt.captions.append(caption)
    output = io.StringIO()
    vtt.write(output)
    return output.getvalue()
