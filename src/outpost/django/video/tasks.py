import io
import logging
import mimetypes
import os.path
import re
import socket
from contextlib import ExitStack
from datetime import timedelta
from itertools import chain
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin

import requests
import streamlink
from bs4 import BeautifulSoup
from celery import (
    shared_task,
    states,
)
from celery.exceptions import Ignore
from celery.schedules import crontab
from django.contrib.sites.models import Site
from django.core.files import File
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from outpost.django.base.tasks import MaintainanceTaskMixin
from outpost.django.base.utils import Process
from outpost.django.campusonline.models import (
    Course,
    CourseGroupTerm,
    Person,
)
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
from .models import (  # EventAudio,; EventVideo,
    Epiphan,
    EpiphanInput,
    EpiphanMedia,
    EpiphanSource,
    Export,
    LiveDeliveryServer,
    LiveEvent,
    LiveViewer,
    Recorder,
    Recording,
)
from .utils import (
    FFMPEGSilenceHandler,
    FFProbeProcess,
    TranscribeException,
    TranscribeMixin,
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


class RecordingTasks:
    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.Recording:process")
    def process(task, pk):
        logger.debug(f"Processing recording: {pk}")
        rec = Recording.objects.get(pk=pk)
        probe = FFProbeProcess("-show_format", "-show_streams", rec.online.path)
        rec.info = probe.run()
        logger.debug(f"Extracted metadata: {rec.info}")
        rec.save()
        logger.info(f"Finished recording: {pk}")

    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.Recording:metadata")
    def metadata(task, pk):
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
        cgt = (
            CourseGroupTerm.objects.filter(
                room=rec.recorder.room.campusonline,
                start__lte=rec.start + timedelta(minutes=30),
                end__gte=rec.end - timedelta(minutes=30),
            )
            .values("start", "end", "person", "title", "coursegroup__course")
            .distinct()
            .first()
        )
        if not cgt:
            logger.warn("No Course Group Term found")
            return
        rec.title = cgt.get("title", None)
        try:
            rec.course = Course.objects.get(pk=cgt.get("coursegroup__course"))
        except Course.DoesNotExist as e:
            logger.warn(f"No Course found: {e}")
            rec.course = None
        try:
            rec.person = Person.objects.get(pk=cgt.get("person"))
        except Person.DoesNotExist as e:
            logger.warn(f"No Person found: {e}")
            rec.person = None
        rec.metadata = {
            "title": rec.title,
            "room": RoomSerializer(rec.recorder.room.campusonline).data,
            "presenter": PersonSerializer(rec.presenter).data
            if rec.presenter
            else None,
            "course": CourseSerializer(rec.course).data,
        }
        rec.save()

    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.Recording:notify")
    def notify(task, pk):
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

    @shared_task(bind=True, ignore_result=True, name=f"{__name__}.Recording:retention")
    def retention(task):
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


class EpiphanTasks:
    firmware_regex = re.compile(r'^Current firmware version: "(?P<version>[\w\.]+)"')

    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.Epiphan:provision")
    def provision(task, pk):
        if not settings.VIDEO_EPIPHAN_PROVISIONING:
            logger.warn("Epiphan provisioning disabled!")
            return
        epiphan = Epiphan.objects.get(pk=pk)
        epiphan.session.post(
            epiphan.url.path("admin/afucfg").as_string(),
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
                "sftpServer": epiphan.server.hostname or socket.getfqdn(),
                "sftpPort": epiphan.server.port,
                "sftpuser": epiphan.pk,
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
        epiphan.session.post(
            epiphan.url.path("admin/timesynccfg").as_string(),
            data={
                "fn": "date",
                "tz": "Europe/Vienna",
                "rdate": "auto",
                "rdate_proto": "NTP",
                "server": epiphan.ntp,
                "ptp_domain": "_DFLT",
                "rdate_secs": "900",
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
            },
        )
        epiphan.session.post(
            epiphan.url.path("admin/sshkeys.cgi").as_string(),
            files={"identity": ("key", epiphan.private_key())},
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

    @shared_task(
        bind=True,
        ignore_result=False,
        name=f"{__name__}.Epiphan:fetch_firmware_version",
    )
    def fetch_firmware_version(task, pk):
        epiphan = Epiphan.objects.get(pk=pk)
        response = epiphan.session.get(
            epiphan.url.path("admin/firmwarecfg").as_string()
        )
        bs = BeautifulSoup(response.content, "lxml")
        text = bs.find(id="fn_upgrade").find("p").text
        version = EpiphanTasks.regex.match(text).groupdict().get("version", "0")
        if epiphan.version != version:
            epiphan.version = version
            epiphan.save()

    @shared_task(bind=True, ignore_result=True, name=f"{__name__}.Epiphan:preview")
    def preview(task):
        if not settings.VIDEO_EPIPHAN_PREVIEW:
            return
        sources = EpiphanSource.objects.filter(
            epiphan__enabled=True, epiphan__online=True
        )
        logger.debug(f"Updating {sources.count()} sources.")
        queue = task.request.delivery_info.get("routing_key")

        for s in sources:
            # TODO: Get queue from current task instead of hardcoding it.
            EpiphanTasks.preview_video.apply_async((s.pk,), queue=queue)
            EpiphanTasks.preview_audio.apply_async((s.pk,), queue=queue)

    @shared_task(
        bind=True, ignore_result=True, name=f"{__name__}.Epiphan:preview_video"
    )
    def preview_video(task, pk):
        source = EpiphanSource.objects.get(pk=pk)
        logger.debug(f"Epiphan source video preview: {source}")
        source.generate_video_preview()

    @shared_task(
        bind=True, ignore_result=True, name=f"{__name__}.Epiphan:preview_audio"
    )
    def preview_audio(task, pk):
        source = EpiphanSource.objects.get(pk=pk)
        logger.debug(f"Epiphan source audio waveform: {source}")
        source.generate_audio_waveform()

    @shared_task(bind=True, ignore_result=True, name=f"{__name__}.Epiphan:reboot")
    def reboot(task):
        epiphans = Epiphan.objects.filter(enabled=True, online=True)
        logger.warning(f"Rebooting Epiphans: {epiphans.count()}")

        for e in epiphans:
            e.reboot()


class EpiphanInputTasks:
    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.EpiphanInput:set")
    def set(task, pk):
        ei = EpiphanInput.objects.get(pk=pk)
        try:
            resp = ei.epiphan.session.post(
                ei.epiphan.url.path("admin/sources")
                .add_path_segment(ei.name)
                .as_string(),
                data={
                    "pfd_form_id": "vsource",
                    "deinterlacing": "on" if ei.deinterlacing else "",
                    "nosignal_src": ei.nosignal_src.name,
                    "nosignal_timeout": ei.nosignal_timeout or "",
                },
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Could not set {ei} on {ei.epiphan}: {e}")
        else:
            logger.debug(f"Set {ei} on {ei.epiphan}")
        finally:
            resp.close()

    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.EpiphanInput:unset")
    def unset(task, pk, name):
        ep = Epiphan.objects.get(pk=pk)
        try:
            resp = ep.session.post(
                ep.url.path("admin/sources").add_path_segment(name).as_string(),
                data={
                    "pfd_form_id": "vsource",
                    "deinterlacing": "",
                    "nosignal_src": "",
                    "nosignal_timeout": "",
                },
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Could not unset {name} on {ep}: {e}")
        else:
            logger.debug(f"Unset {name} on {ep}")
        finally:
            resp.close()


class EpiphanMediaTasks:
    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.EpiphanMedia:upload")
    def upload(task, pk):
        em = EpiphanMedia.objects.get(pk=pk)
        try:
            resp = em.epiphan.session.post(
                em.epiphan.url.path("admin/media").as_string(),
                files={"1": (em.name, em.image.open("rb"))},
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Could not upload {em} to {em.epiphan}: {e}")
        else:
            logger.debug(f"Uploaded {em} to {em.epiphan}")
        finally:
            resp.close()

    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.EpiphanMedia:remove")
    def remove(task, pk, name):
        ep = Epiphan.objects.get(pk=pk)
        try:
            resp = ep.session.delete(
                ep.url.path("api/media/files").add_path_segment(name).as_string()
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Could not remove {name} from {ep}: {e}")
        else:
            logger.debug(f"Uploaded {name} to {ep}")
        finally:
            resp.close()


class ExportTasks:
    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.Export:create")
    def create(task, pk, exporter, base_uri):
        def progress(action, current, maximum):
            logger.debug(f"Progress: {action} {current}/{maximum}")
            if task.request.id:
                task.update_state(
                    state="PROGRESS",
                    meta={"action": action, "current": current, "maximum": maximum},
                )

        classes = Export.__subclasses__()
        exporters = {c.__name__: c for c in classes}
        if exporter not in exporters:
            task.update_state(
                state=states.FAILURE, meta=f"Unknown exporter: {exporter}"
            )
            raise Ignore()
        try:
            rec = Recording.objects.get(pk=pk)
        except Recording.DoesNotExist:
            task.update_state(state=states.FAILURE, meta=f"Unknown recording: {pk}")
            raise Ignore()
        cls = exporters.get(exporter)
        logger.info("Recording {} export requested: {}".format(rec.pk, cls))
        (inst, _) = cls.objects.get_or_create(recording=rec)
        if not inst.data:
            logger.info(f"Recording {rec.pk} processing: {cls}")
            inst.process(progress)
            logger.debug(f"Recording {rec.pk} download URL: {inst.data.url}")
        return urljoin(base_uri, inst.data.url)

    @shared_task(bind=True, ignore_result=True, name=f"{__name__}.Export:cleanup")
    def cleanup(task):
        expires = timezone.now() - timedelta(hours=24)
        for e in Export.objects.filter(modified__lt=expires):
            logger.debug(f"Remove expired export: {e}")
            e.delete()


class TranscribeTask(TranscribeMixin):
    def run(self, pk, **kwargs):
        from .models import (
            Event,
            TranscribeLanguage,
        )

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


class TranscribeResultTask(TranscribeMixin):
    ignore_result = False
    default_retry_delay = 120
    max_retries = 120

    def run(self, job, pk, **kwargs):
        from .models import (
            Event,
            Transcript,
        )

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


class AuphonicTasks:

    format = settings.VIDEO_AUPHONIC_FORMAT
    auth = (settings.VIDEO_AUPHONIC_USERNAME, settings.VIDEO_AUPHONIC_PASSWORD)

    @shared_task(
        bind=True,
        ignore_result=False,
        default_retry_delay=120,
        max_retries=120,
        name=f"{__name__}.Auphonic:process",
    )
    def process(task, pk):
        logger.info(f"Starting Auphonic processing: {pk}")
        url = (
            URL(settings.VIDEO_AUPHONIC_URL)
            .add_path_segment("simple")
            .add_path_segment("productions.json")
        )
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
            prefix="auphonic-input-", suffix=f".{AuphonicTasks.format}"
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
                AuphonicTasks.format,
                output.name,
            )
            silence = FFMPEGSilenceHandler()
            extract.handler(silence)
            extract.run()
            ratio = silence.overall() / float(rec.info.get("format").get("duration"))
            if ratio > settings.VIDEO_AUPHONIC_SILENCE_THRESHOLD:
                logger.warn(
                    f"Silent audio in recording {rec} detected. Skipping Auphonic processing."
                )
                return
            mime, _ = mimetypes.guess_type(output.name)
            with open(output.name, "rb") as inp:
                data = MultipartEncoder(
                    fields={
                        "preset": rec.recorder.auphonic,
                        "title": str(rec.pk),
                        "action": "start",
                        "input_file": (f"{rec.pk}.{AuphonicTasks.format}", inp, mime),
                    }
                )
                headers = {"Content-Type": data.content_type}
                try:
                    with requests.post(
                        url.as_string(),
                        auth=AuphonicTasks.auth,
                        data=data,
                        headers=headers,
                    ) as resp:
                        resp.raise_for_status()
                        uuid = resp.json().get("data").get("uuid")
                        logger.info(f"Queued Auphonic production with UUID {uuid}")
                        return uuid
                except requests.exceptions.RequestException as e:
                    logger.error(f"Could not upload audio data to Auphonic: {e}")
                    raise task.retry()

    @shared_task(
        bind=True,
        ignore_result=True,
        default_retry_delay=120,
        max_retries=120,
        name=f"{__name__}.Auphonic:retreive",
    )
    def retrieve(task, job, pk):
        logger.info(f"Fetching Auphonic result for {pk} from {job}")
        url = (
            URL(settings.VIDEO_AUPHONIC_URL)
            .add_path_segment("production")
            .add_path_segment(f"{job}.json")
        )
        if not job:
            logger.info(f"No job ID specified for {pk}, skipping Auphonic result.")
            return
        try:
            with requests.get(url.as_string(), auth=AuphonicTasks.auth) as resp:
                resp.raise_for_status()
                data = resp.json().get("data")
        except requests.exceptions.RequestException as e:
            logger.error(f"Could not fetch Auphonic result for {job}: {e}")
            raise task.retry()
        status = data.get("status", None)
        if not status:
            logger.warn(f"Unable to determine status for Auphonic: {job}")
            raise task.retry()
        if status == 2:
            logger.error(f"Error in production on Auphonic: {job}")
            return
        if status == 9:
            logger.error(f"Incomplete production on Auphonic: {job}")
            return
        if status != 3:
            logger.info(f"Still processing on Auphonic: {job}")
            raise task.retry()
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
                    with requests.get(
                        download, stream=True, auth=AuphonicTasks.auth
                    ) as resp:
                        resp.raise_for_status()
                        for chunk in resp.iter_content(
                            chunk_size=settings.VIDEO_AUPHONIC_CHUNK_SIZE
                        ):
                            if chunk:
                                output.write(chunk)
                        output.flush()
                except requests.exceptions.RequestException as e:
                    logger.error(f"Could not fetch Auphonic result for {job}: {e}")
                    raise task.retry()
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
            with requests.delete(url.as_string(), auth=AuphonicTasks.auth) as resp:
                resp.raise_for_status()
                logger.debug(f"Removed production from Auphonic: {job}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Could not remove Auphonic production for {job}: {e}")


class LiveEventTasks:
    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.LiveEvent:cleanup")
    def cleanup(task, pk):
        logger.info(f"Cleaning up live event: {pk}")
        event = LiveEvent.objects.get(pk=pk)
        for v in event.liveviewer_set.select_related("event").all():
            v.disable()
            v.collect()
            v.save()
            v.cleanup()

    @shared_task(bind=True, ignore_result=False, name=f"{__name__}.LiveEvent:is_alive")
    def is_alive(task):
        for le in LiveEvent.objects.filter(end=None).exclude(job=None):
            if not le.job.is_alive():
                le.stop()

    @shared_task(
        bind=True, ignore_result=False, name=f"{__name__}.LiveEvent:ready_to_publish"
    )
    def ready_to_publish(task, pk):
        le = LiveEvent.objects.get(pk=pk)
        if le.end:
            return
        for ds in le.delivery.all():
            v = LiveViewer.objects.create(event=le, delivery=ds)
            try:
                for ls in le.livestream_set.all():
                    url = ls.viewer(viewer=v)
                    streamlink.streams(url)
            except streamlink.StreamlinkError as e:
                task.retry(exc=e, countdown=1, max_retries=300)
            finally:
                v.disable()
                v.delete()
        # Notify portal
        for portal in le.channel.portals.all():
            portal.start(le)
        le.begin = timezone.now()
        le.save()


class LiveDeliveryServerTasks:
    @shared_task(
        bind=True, ignore_result=False, name=f"{__name__}.LiveDeliveryServer:check"
    )
    def check(task):
        for d in LiveDeliveryServer.objects.all():
            if not d.is_alive():
                if d.online:
                    logger.warning(f"Delivery server {d} offline")
                    d.online = False
                    d.save()
            else:
                if not d.online:
                    logger.info(f"Delivery server {d} online")
                    d.online = True
                    d.save()
