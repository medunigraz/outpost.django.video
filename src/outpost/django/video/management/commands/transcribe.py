import argparse
import logging
import os
import re
from contextlib import ExitStack
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from django.core.files.base import File
from django.core.management.base import BaseCommand
from outpost.django.base.utils import Process
from tenacity import (
    RetryError,
    Retrying,
    after_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from tqdm import tqdm

from ...models import TranscribeLanguage
from ...utils import FFProbeProcess, TranscribeException, TranscribeMixin, json2vtt

logger = logging.getLogger(__name__)


class Command(TranscribeMixin, BaseCommand):
    help = "Transcribe audio to WebVTT."

    def add_arguments(self, parser):
        parser.add_argument("-l", type=str, dest="language")
        parser.add_argument("media", type=str, nargs="+")

    def handle(self, *args, **options):
        def check_media(p):
            if os.path.exists(p):
                return p
            logger.warn(f"File not found, skipping: {p}")
            return None

        lang = TranscribeLanguage.objects.get(code=options["language"])
        media = filter(check_media, options["media"])
        jobs = [(str(uuid4()), Path(m)) for m in media]
        results = list()
        for j, p in tqdm(jobs, desc="Transcribing", unit="files"):
            logger.debug(f"Extracting audio: {p}")
            probe = FFProbeProcess("-show_format", "-show_streams", str(p))
            info = probe.run()
            audio = list(
                map(
                    lambda s: "[i:{id}]".format(id=s.get("index")),
                    filter(
                        lambda s: s.get("codec_type") == "audio", info.get("streams")
                    ),
                )
            )
            with NamedTemporaryFile(prefix="transcribe-upload-", suffix=".flac") as t:
                args = (
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "warning",
                    "-i",
                    str(p),
                    "-filter_complex",
                    "{streams} amix=inputs={count}".format(
                        streams="".join(audio), count=len(audio)
                    ),
                    "-vn",
                    "-c:a",
                    "flac",
                    t.name,
                )
                extract = Process(*args)
                extract.run()
                logger.debug(f"Transcribing audio: {p}")
                try:
                    self.transcribe(j, t.name, lang.code)
                except TranscribeException as e:
                    logger.warn(f"Could not start transcription job: {e}")
                    continue
                results.append((j, p))
        for j, p in tqdm(results, desc="Retrieving", unit="files"):
            retry = Retrying(
                stop=stop_after_attempt(120),
                wait=wait_fixed(120),
                retry=retry_if_exception_type(TranscribeException),
                reraise=True,
                after=after_log(logger, logging.DEBUG),
            )
            try:
                for attempt in retry:
                    with attempt:
                        (start, stop, result) = self.retrieve(j)
            except TranscribeException as e:
                logger.error(f"Failed to retrieve result for job {j}: {e}")
                continue
            with p.with_suffix(".vtt").open("w", encoding="utf-8") as vtt:
                logger.debug(f"Writing WebVTT from job {j} to {vtt}")
                vtt.write(json2vtt(result.get("results").get("items")))
