import logging
import re
import socket
from datetime import timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from celery import states
from celery.exceptions import Ignore
from celery.schedules import crontab
from celery.task import PeriodicTask, Task
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from pint import UnitRegistry

from outpost.django.base.tasks import MaintainanceTaskMixin
from outpost.django.campusonline.models import Course, CourseGroupTerm, Person
from outpost.django.campusonline.serializers import (
    CourseSerializer,
    PersonSerializer,
    RoomSerializer,
)

from .utils import FFProbeProcess

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
                        "url": settings.OUTPOST["crates_recording_url"].format(
                            pk=rec.pk
                        ),
                    },
                ),
                settings.SERVER_EMAIL,
                [user.email],
                headers={"X-Recording-ID": rec.pk},
            ).send()


class EpiphanProvisionTask(Task):
    def run(self, pk, **kwargs):
        if not settings.OUTPOST.get("epiphan_provisioning"):
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
