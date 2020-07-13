import io
import mimetypes
import logging
import os.path
import re
import socket
from contextlib import ExitStack
from datetime import timedelta
from itertools import chain
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from celery import states
from celery.exceptions import Ignore
from celery.schedules import crontab
from celery.task import PeriodicTask, Task
from django.contrib.sites.models import Site
from django.core.files import File
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from outpost.django.base.tasks import MaintainanceTaskMixin
from outpost.django.base.utils import Process
from outpost.django.campusonline.models import Course, CourseGroupTerm, Person
from outpost.django.campusonline.serializers import (
    CourseSerializer,
    PersonSerializer,
    RoomSerializer,
)
from pint import UnitRegistry
from purl import URL
from requests.auth import HTTPBasicAuth
from requests_toolbelt.multipart.encoder import MultipartEncoder

from .conf import settings
from .utils import FFProbeProcess, FFMPEGSilenceHandler, TranscribeException, TranscribeMixin

from .models import (  # EventAudio,; EventVideo,
    Epiphan,
    EpiphanSource,
    Export,
    Recorder,
    Recording,
)

logger = logging.getLogger(__name__)

ureg = UnitRegistry()

# Metadata:
# ffprobe -v quiet -print_format json -show_format -show_streams \
#       Recorder_Aug07_12-56-01.ts

# Side-by-Side:
# ffmpeg -i Recorder_Aug07_12-56-01.ts -filter_complex \
#       '[i:0x100][i:0x102]hstack=inputs=2[v];[i:0x101][i:0x103]amerge[a]' \
#       -map '[v]' -map '[a]' -ac 2 output.mp4'

# Split video in two:
# ffmpeg -i output.mp4 -filter_complex \
#        '[0:v]crop=iw/2:ih:0:0[left];[0:v]crop=iw/2:ih:iw/2:0[right]' \
#        -map '[left]' left.mp4 -map '[right]' right.mp4

# OCR:
# ffprobe -v quiet -print_format json -show_entries frame_tags:frame \
#        -f lavfi -i "movie=video-0x100.mp4,select='eq(pict_type,I)',hue=s=0,"\
#                    "atadenoise,select='gt(scene,0.02)',ocr"))'

# Scene extraction
# ffmpeg -i video-0x100.mp4 -filter:v \
#        "select='eq(pict_type,I)',atadenoise,select='eq(t,70)+eq(t,147)"\
#         "+eq(t,170)+eq(t,190)+eq(t,261)+eq(t,269)+eq(t,270)+eq(t,275)"\
#         "+eq(t,287)+eq(t,361)+eq(t,363)+eq(t,365)'" -vsync 0 frames/%05d.jpg'


class VideoTaskMixin:
    options = {"queue": "video"}
    queue = "video"


class ProcessRecordingTask(VideoTaskMixin, Task):
    ignore_result = False

    def run(self, pk, **kwargs):
        logger.debug(f"Processing recording: {pk}")
        rec = Recording.objects.get(pk=pk)
        probe = FFProbeProcess("-show_format", "-show_streams", rec.online.path)
        rec.info = probe.run()
        logger.debug(f"Extracted metadata: {rec.info}")
        rec.save()
        logger.info(f"Finished recording: {pk}")


class MetadataRecordingTask(MaintainanceTaskMixin, Task):
    ignore_result = False

    def run(self, pk, **kwargs):
        logger.debug(f"Fetching metadata: {pk}")
        rec = Recording.objects.get(pk=pk)
        if not rec.start:
            logger.warn(f"No start time recorded: {pk}")
            return
        if not rec.end:
            logger.warn(f"No end time found: {pk}")
            return
        if not rec.recorder.room:
            logger.warn(f"No room found: {pk}")
            return
        data = MetadataRecordingTask.find(
            rec.recorder.room.campusonline,
            rec.start + timedelta(minutes=30),
            rec.end - timedelta(minutes=30),
        )
        if not data:
            return
        (rec.title, rec.course, rec.presenter) = data
        rec.metadata = {
            "title": rec.title,
            "room": RoomSerializer(rec.recorder.room.campusonline).data,
            "presenter": PersonSerializer(rec.presenter).data
            if rec.presenter
            else None,
            "course": CourseSerializer(rec.course).data,
        }
        rec.save()

    @staticmethod
    def find(room, start, end):
        cgt = (
            CourseGroupTerm.objects.filter(room=room, start__lte=start, end__gte=end)
            .values("start", "end", "person", "title", "coursegroup__course")
            .distinct()
            .first()
        )
        if not cgt:
            logger.warn("No Course Group Term found")
            return
        course = None
        try:
            course = Course.objects.get(pk=cgt.get("coursegroup__course"))
        except Course.DoesNotExist as e:
            logger.warn(f"No Course found: {e}")
        person = None
        try:
            person = Person.objects.get(pk=cgt.get("person"))
        except Person.DoesNotExist as e:
            logger.warn(f"No Person found: {e}")
        return (cgt.get("title", None), course, person)


class NotifyRecordingTask(MaintainanceTaskMixin, Task):
    ignore_result = False

    def run(self, pk, **kwargs):
        logger.debug(f"Sending notifications: {pk}")
        rec = Recording.objects.get(pk=pk)
        for notification in rec.recorder.epiphan.notifications.all():
            user = notification.user
            if not user.email:
                logger.warn(f"{user} wants notifications but has no email")
                continue
            logger.debug(f"Sending {rec} notification to {user.email}")
            EmailMessage(
                _(f"New recording from {rec.recorder}"),
                render_to_string(
                    "video/mail/recording.txt",
                    {
                        "recording": rec,
                        "user": user,
                        "site": Site.objects.get_current(),
                        "url": settings.VIDEO_CRATES_RECORDING_URL.format(pk=rec.pk),
                    },
                ),
                settings.SERVER_EMAIL,
                [user.email],
                headers={"X-Recording-ID": rec.pk},
            ).send()


class EpiphanProvisionTask(Task):
    def run(self, pk, **kwargs):
        if not settings.VIDEO_EPIPHAN_PROVISIONING:
            logger.warn("Epiphan provisioning disabled!")
            return
        self.epiphan = Epiphan.objects.get(pk=pk)
        self.epiphan.session.post(
            self.epiphan.url.path("admin/afucfg").as_string(),
            data={
                "pfd_form_id": "fn_afu",
                "afuEnable": "on",
                "afuProtocol": "sftp",
                "afuInterval": 0,
                "afuRemotePath": "",
                "remove-source-files": "on",
                "mark-downloaded": None,
                "ftpServer": None,
                "ftpPort": None,
                "ftpuser": None,
                "ftppasswd": None,
                "ftptmpfile": None,
                "cifsPort": None,
                "cifsServer": None,
                "cifsShare": None,
                "cifsDomain": None,
                "cifsUser": None,
                "cifsPasswd": None,
                "cifstmpfile": None,
                "rsyncServer": None,
                "rsyncModule": None,
                "rsyncUser": None,
                "rsyncPassword": None,
                "rsyncChecksum": None,
                "scpServer": None,
                "scpPort": None,
                "scpuser": None,
                "scppasswd": None,
                "sftpServer": self.epiphan.server.hostname or socket.getfqdn(),
                "sftpPort": self.epiphan.server.port,
                "sftpuser": self.epiphan.pk,
                "sftppasswd": None,
                "sftptmpfile": None,
                "s3Region": None,
                "s3Bucket": None,
                "s3Key": None,
                "s3Secret": None,
                "s3Token": None,
                "preserve-channel-name": None,
            },
        )
        now = timezone.now()
        self.epiphan.session.post(
            self.epiphan.url.path("admin/timesynccfg").as_string(),
            data={
                "fn": "date",
                "tz": "Europe/Vienna",
                "rdate": "auto",
                "rdate_proto": "NTP",
                "server": self.epiphan.ntp,
                "ptp_domain": "_DFLT",
                "rdate_secs": "900",
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
            },
        )
        self.epiphan.session.post(
            self.epiphan.url.path("admin/sshkeys.cgi").as_string(),
            files={"identity": ("key", self.epiphan.private_key())},
            data={"command": "add"},
        )

    def createRecorder(self, name):
        self.epiphan.session.post(self.epiphan.url.path("api/recorders").as_string())

    def renameRecorder(self, pk, name):
        self.epiphan.session.post(
            self.epiphan.url.path("admin/ajax/rename_channel.cgi").as_string(),
            data={"channel": pk, "id": "channelname", "value": name},
        )

    def setRecorderChannels(self, pk, use_all=True, channels=[]):
        self.epiphan.session.post(
            self.epiphan.url.path(f"admin/recorder{pk}/archive").as_string(),
            data={
                "pfd_form_id": "recorder_channels",
                "rc[]": "all" if use_all else channels,
            },
        )

    def setRecorderSettings(self, pk, recorder):
        hours, remainder = divmod(recorder.timelimit.total_seconds(), 3600)
        minutes, seconds = map(lambda x: str(x).rjust(2, "0"), divmod(remainder, 60))
        self.epiphan.session.post(
            self.epiphan.url.path(f"admin/recorder{pk}/archive").as_string(),
            data={
                "afu_enabled": "",
                "exclude_singletouch": "",
                "output_format": "ts",
                "pfd_form_id": "rec_settings",
                "sizelimit": int(ureg(recorder.sizelimit).to("byte").m),
                "svc_afu_enabled": "on" if recorder.auto_upload else "",
                "timelimit": f"{hours}:{minutes}:{seconds}",
                "upnp_enabled": "",
                "user_prefix": "",
            },
        )

    def setTime(self, pk, use_all=True, channels=[]):
        now = timezone.now()
        self.epiphan.session.post(
            self.epiphan.url.path(f"admin/recorder{pk}/archive").as_string(),
            data={
                "date": now.strftime("%Y-%m-%d"),
                "fn": "date",
                "ptp_domain": "_DFLT",
                "rdate": "auto",
                "rdate_proto": "NTP",
                "rdate_secs": 900,
                "server": self.epiphan.ntp,
                "time": now.strftime("%H:%M:%S"),
                "tz": "Europe/Vienna",
            },
        )


class EpiphanFirmwareTask(MaintainanceTaskMixin, PeriodicTask):
    run_every = timedelta(hours=12)
    ignore_result = False
    regex = re.compile(r'^Current firmware version: "(?P<version>[\w\.]+)"')

    def run(self, pk, **kwargs):
        epiphan = Epiphan.objects.get(pk=pk)
        response = epiphan.session.get(
            self.epiphan.url.path("admin/firmwarecfg").as_string()
        )
        bs = BeautifulSoup(response.content, "lxml")
        text = bs.find(id="fn_upgrade").find("p").text
        version = self.regex.match(text).groupdict().get("version", "0")
        if epiphan.version != version:
            epiphan.version = version
            epiphan.save()


class ExportTask(VideoTaskMixin, Task):
    def run(self, pk, exporter, base_uri, **kwargs):
        classes = Export.__subclasses__()
        exporters = {c.__name__: c for c in classes}
        if exporter not in exporters:
            self.update_state(
                state=states.FAILURE, meta=f"Unknown exporter: {exporter}"
            )
            raise Ignore()
        try:
            rec = Recording.objects.get(pk=pk)
        except Recording.DoesNotExist:
            self.update_state(state=states.FAILURE, meta=f"Unknown recording: {pk}")
            raise Ignore()
        cls = exporters.get(exporter)
        logger.info("Recording {} export requested: {}".format(rec.pk, cls))
        (inst, _) = cls.objects.get_or_create(recording=rec)
        if not inst.data:
            logger.info(f"Recording {rec.pk} processing: {cls}")
            inst.process(self.progress)
            logger.debug(f"Recording {rec.pk} download URL: {inst.data.url}")
        return urljoin(base_uri, inst.data.url)

    def progress(self, action, current, maximum):
        logger.debug(f"Progress: {action} {current}/{maximum}")
        if self.request.id:
            self.update_state(
                state="PROGRESS",
                meta={"action": action, "current": current, "maximum": maximum},
            )


class ExportCleanupTask(MaintainanceTaskMixin, PeriodicTask):
    run_every = timedelta(hours=1)
    ignore_result = False

    def run(self, **kwargs):
        expires = timezone.now() - timedelta(hours=24)
        for e in Export.objects.filter(modified__lt=expires):
            logger.debug(f"Remove expired export: {e}")
            e.delete()


class RecordingRetentionTask(MaintainanceTaskMixin, PeriodicTask):
    run_every = timedelta(hours=1)
    ignore_result = False

    def run(self, **kwargs):
        recorders = Recorder.objects.filter(enabled=True).exclude(retention=None)
        logger.info(f"Enforcing retention on {recorders.count()} sources")
        now = timezone.now()

        for r in recorders:
            for rec in Recording.objects.filter(
                recorder=r, created__lt=(now - r.retention)
            ):
                logger.warn(
                    f"Removing recording {rec.pk} from {rec.created} after retention"
                )
                rec.delete()


class EpiphanSourceTask(MaintainanceTaskMixin, PeriodicTask):
    run_every = timedelta(minutes=1)
    ignore_result = True

    def run(self, **kwargs):
        if not settings.VIDEO_EPIPHAN_PREVIEW:
            return
        sources = EpiphanSource.objects.filter(
            epiphan__enabled=True, epiphan__online=True
        )
        logger.info(f"Updating {sources.count()} sources.")

        for s in sources:
            EpiphanSourceVideoPreviewTask().delay(s.pk)
            EpiphanSourceAudioWaveformTask().delay(s.pk)


class EpiphanSourceVideoPreviewTask(MaintainanceTaskMixin, Task):
    ignore_result = True

    def run(self, pk, **kwargs):
        source = EpiphanSource.objects.get(pk=pk)
        logger.info(f"Epiphan source video preview: {source}")
        source.generate_video_preview()


class EpiphanSourceAudioWaveformTask(MaintainanceTaskMixin, Task):
    ignore_result = True

    def run(self, pk, **kwargs):
        source = EpiphanSource.objects.get(pk=pk)
        logger.info(f"Epiphan source audio waveform: {source}")
        source.generate_audio_waveform()


class EpiphanRebootTask(MaintainanceTaskMixin, PeriodicTask):
    run_every = crontab(hour=5, minute=0)
    ignore_result = False

    def run(self, **kwargs):
        epiphans = Epiphan.objects.filter(enabled=True, online=True)
        logger.info(f"Rebooting Epiphans: {epiphans.count()}")

        for e in epiphans:
            e.reboot()


class TranscribeTask(TranscribeMixin, MaintainanceTaskMixin, Task):
    ignore_result = False

    def run(self, pk, **kwargs):
        from .models import TranscribeLanguage, Event

        if "language" in kwargs:
            lang = TranscribeLanguage.objects.get(code=kwargs.get("lanugage"))
        else:
            lang = TranscribeLanguage.objects.first()
        logger.debug(f"Transcribing audio: {pk}")
        event = Event.objects.get(pk=pk)
        url = (
            URL(event.opencast.url)
            .add_path_segment("events")
            .add_path_segment(event.pk)
            .add_path_segment("publications")
        )
        try:
            resp = requests.get(url.as_string())
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Could not fetch Opencast publications for {event}: {e}")
        publications = resp.json()
        candidate = max(
            chain.from_iterable(
                filter(
                    lambda m: m.get("has_audio", False),
                    map(publications, lambda p: p.get("media", [])),
                )
            ),
            key=lambda m: m.get("bitrate"),
        )
        result = self.transcribe(self.request.id, audio.file, lang.code)
        return result


class TranscribeResultTask(TranscribeMixin, MaintainanceTaskMixin, Task):
    ignore_result = False
    default_retry_delay = 120
    max_retries = 120

    def run(self, job, pk, **kwargs):
        from .models import Transcript, Event

        logger.debug(f"Fetching transcription result for {pk} from {job}")
        event = Event.objects.get(pk=pk)
        try:
            (start, stop, result) = self.retrieve(job)
        except TranscribeException as e:
            logger.error(f"Could not fetch transcription results for {job}: {e}")
            raise self.retry()
        transcript, created = Transcript.objects.update_or_create(
            event=event, defaults={"data": result, "duration": stop - start}
        )
        if created:
            logger.info(f"Created new transcription for {event}")
        else:
            logger.info(f"Updated transcription for {event}")
        return transcript.pk


class AuphonicProcessTask(MaintainanceTaskMixin, Task):
    ignore_result = False
    default_retry_delay = 120
    max_retries = 120

    format = settings.VIDEO_AUPHONIC_FORMAT
    url = (
        URL(settings.VIDEO_AUPHONIC_URL)
        .add_path_segment("simple")
        .add_path_segment("productions.json")
    )
    auth = (settings.VIDEO_AUPHONIC_USERNAME, settings.VIDEO_AUPHONIC_PASSWORD)

    def run(self, pk, **kwargs):
        logger.info(f"Starting Auphonic processing: {pk}")
        rec = Recording.objects.get(pk=pk)
        audio = list(
            map(
                lambda s: "[i:{id}]".format(id=s.get("id")),
                filter(
                    lambda s: s.get("codec_type") == "audio", rec.info.get("streams")
                ),
            )
        )
        with NamedTemporaryFile(
            prefix="auphonic-input-", suffix=f".{self.format}"
        ) as output:
            extract = Process(
                "ffmpeg",
                "-y",
                "-i",
                rec.online.path,
                "-filter_complex",
                "{streams} amix=inputs={count},silencedetect".format(
                    streams="".join(audio), count=len(audio)
                ),
                "-vn",
                "-c:a",
                self.format,
                output.name,
            )
            silence = FFMPEGSilenceHandler()
            extract.handler(silence)
            extract.run()
            ratio = silence.overall() / float(rec.info.get('format').get('duration'))
            if ratio > settings.VIDEO_AUPHONIC_SILENCE_THRESHOLD:
                logger.warn(f"Silent audio in recording {rec} detected. Skipping Auphonic processing.")
                return
            mime, _ = mimetypes.guess_type(output.name)
            with open(output.name, "rb") as inp:
                data = MultipartEncoder(
                    fields={
                        "preset": rec.recorder.auphonic,
                        "title": str(rec.pk),
                        "action": "start",
                        "input_file": (f"{rec.pk}.{self.format}", inp, mime),
                    }
                )
                headers = {"Content-Type": data.content_type}
                try:
                    with requests.post(
                        self.url.as_string(), auth=self.auth, data=data, headers=headers
                    ) as resp:
                        resp.raise_for_status()
                        uuid = resp.json().get("data").get("uuid")
                        logger.info(f"Queued Auphonic production with UUID {uuid}")
                        return uuid
                except requests.exceptions.RequestException as e:
                    logger.error(f"Could not upload audio data to Auphonic: {e}")
                    raise self.retry()


class AuphonicResultTask(MaintainanceTaskMixin, Task):
    ignore_result = True
    default_retry_delay = 120
    max_retries = 120

    url = URL(settings.VIDEO_AUPHONIC_URL).add_path_segment("production")
    auth = (settings.VIDEO_AUPHONIC_USERNAME, settings.VIDEO_AUPHONIC_PASSWORD)

    def run(self, job, pk, **kwargs):
        logger.info(f"Fetching Auphonic result for {pk} from {job}")
        if not job:
            logger.info(f"No job ID specified for {pk}, skipping Auphonic result.")
            return
        url = self.url.add_path_segment(f"{job}.json")
        try:
            with requests.get(url.as_string(), auth=self.auth) as resp:
                resp.raise_for_status()
                data = resp.json().get("data")
        except requests.exceptions.RequestException as e:
            logger.error(f"Could not fetch Auphonic result for {job}: {e}")
            raise self.retry()
        status = data.get("status", None)
        if not status:
            logger.warn(f"Unable to determine status for Auphonic: {job}")
            raise self.retry()
        if status == 2:
            logger.error(f"Error in production on Auphonic: {job}")
            return
        if status == 9:
            logger.error(f"Incomplete production on Auphonic: {job}")
            return
        if status != 3:
            logger.info(f"Still processing on Auphonic: {job}")
            raise self.retry()
        results = list(
            map(
                lambda o: (
                    o,
                    NamedTemporaryFile(
                        prefix="auphonic-output-", suffix=".{}".format(o.get("ending"))
                    ),
                ),
                data.get("output_files"),
            )
        )
        with ExitStack() as stack:
            for result, output in results:
                stack.enter_context(output)
                download = result.get("download_url")
                try:
                    logger.debug(f"Downloading Auphonic media: {download}")
                    with requests.get(download, stream=True, auth=self.auth) as resp:
                        resp.raise_for_status()
                        for chunk in resp.iter_content(
                            chunk_size=settings.VIDEO_AUPHONIC_CHUNK_SIZE
                        ):
                            if chunk:
                                output.write(chunk)
                        output.flush()
                except requests.exceptions.RequestException as e:
                    logger.error(f"Could not fetch Auphonic result for {job}: {e}")
                    raise self.retry()
            rec = Recording.objects.get(pk=pk)
            inp, maps = map(
                chain.from_iterable,
                zip(
                    *(
                        (("-i", o.name), ("-map", f"{i + 1}:a"))
                        for i, o in enumerate((o for _, o in results))
                    )
                ),
            )
            with NamedTemporaryFile(prefix="auphonic-merged-", suffix=".ts") as output:
                args = ["ffmpeg", "-y", "-i", rec.online.path]
                args.extend(inp)
                args.extend(["-map", "0:v", "-map", "0:a"])
                args.extend(maps)
                args.extend(["-c:v", "copy", "-c:a", "aac", output.name])
                merge = Process(*args)
                merge.run()
                rec.online.save(output.name, File(output.file))
        try:
            with requests.delete(url.as_string(), auth=self.auth) as resp:
                resp.raise_for_status()
                logger.debug(f"Removed production from Auphonic: {job}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Could not remove Auphonic production for {job}: {e}")
