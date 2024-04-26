import logging
import os
import re
import subprocess
from base64 import b64encode
from collections import Counter
from datetime import timedelta
from functools import (
    lru_cache,
    partial,
    reduce,
)
from hashlib import sha256
from tempfile import (
    NamedTemporaryFile,
    TemporaryDirectory,
)
from zipfile import (
    ZIP_DEFLATED,
    ZipFile,
)

import asyncssh
import certifi
import requests
import streamlink
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.postgres.fields import JSONField
from django.contrib.sites.models import Site
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.validators import RegexValidator
from django.db import (
    models,
    transaction,
)
from django.template import (
    Context,
    Template,
)
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import ugettext
from django.utils.translation import ugettext_lazy as _
from django_countries.fields import CountryField
from django_extensions.db.fields import ShortUUIDField
from django_extensions.db.models import TimeStampedModel
from django_prometheus.models import ExportModelOperationsMixin
from django_sshworker.models import (
    Job,
    JobConstraint,
    Resource,
)
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill
from markupfield.fields import MarkupField
from memoize import (
    delete_memoized,
    memoize,
)
from netfields import (
    CidrAddressField,
    InetAddressField,
    NetManager,
)
from openpyxl import Workbook
from openpyxl.writer.excel import ExcelWriter
from ordered_model.models import OrderedModel
from outpost.django.base.decorators import signal_connect
from outpost.django.base.models import NetworkedDeviceMixin
from outpost.django.base.utils import (
    Process,
    Uuid4Upload,
)
from outpost.django.base.validators import RedisURLValidator
from outpost.django.campusonline.models import (
    Course,
    CourseGroupTerm,
    Person,
)
from polymorphic.models import PolymorphicModel
from purl import URL
from redis import Redis
from tenacity import (
    RetryError,
    Retrying,
    stop_after_attempt,
    wait_fixed,
)

from .conf import settings
from .utils import FFMPEGProgressHandler

logger = logging.getLogger(__name__)


@signal_connect
class Server(models.Model):
    hostname = models.CharField(max_length=128, blank=True)
    port = models.PositiveIntegerField(default=2022)
    key = models.BinaryField(null=False)
    enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = (("hostname", "port"),)
        ordering = ("hostname", "port")

    def fingerprint(self):
        if not self.key:
            return None
        k = asyncssh.import_private_key(self.key.tobytes())
        d = sha256(k.get_ssh_public_key()).digest()
        f = b64encode(d).replace(b"=", b"").decode("utf-8")
        return "SHA256:{}".format(f)

    def pre_save(self, *args, **kwargs):
        if self.key:
            return
        pk = asyncssh.generate_private_key("ssh-rsa")
        self.key = pk.export_private_key()

    def ping(self):
        try:
            cache.set("outpost-video-server-{}".format(str(self)), True, timeout=10)
        except Exception:
            logger.error(f"Could not set active state for {self}")

    @property
    def active(self):
        try:
            return cache.get("outpost-video-server-{}".format(str(self)), False)
        except Exception:
            return False

    def __str__(self):
        if self.hostname:
            return "{s.hostname}:{s.port}".format(s=self)
        return "*:{s.port}".format(s=self)


class Recorder(NetworkedDeviceMixin, PolymorphicModel):
    name = models.CharField(max_length=128, blank=False, null=False)
    room = models.ForeignKey(
        "geo.Room", null=True, blank=True, on_delete=models.SET_NULL
    )
    notifications = GenericRelation("base.Notification")
    retention = models.DurationField(default=None, null=True, blank=True)
    auphonic = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ("name", "hostname")

    def __str__(self):
        return self.name


@signal_connect
class Epiphan(Recorder):
    username = models.CharField(max_length=128, blank=False, null=False)
    password = models.CharField(max_length=128, blank=False, null=False)
    server = models.ForeignKey(
        "Server", related_name="+", null=True, blank=True, on_delete=models.SET_NULL
    )
    key = models.BinaryField(null=False)
    provision = models.BooleanField(default=False)
    ntp = models.CharField(
        max_length=128,
        default="0.pool.ntp.org 1.pool.ntp.org 2.pool.ntp.org 3.pool.ntp.org",
    )
    version = models.CharField(max_length=16, default="0")

    def fingerprint(self):
        if not self.key:
            return None
        k = asyncssh.import_private_key(self.key.tobytes())
        d = sha256(k.public_data).digest()
        f = b64encode(d).replace(b"=", b"").decode("utf-8")
        return "SHA256:{}".format(f)

    def private_key(self):
        return self.key.tobytes().decode("ascii")

    def post_init(self, *args, **kwargs):
        self.session = requests.Session()
        if self.username and self.password:
            self.session.auth = (self.username, self.password)
        self.url = URL(scheme="http", host=self.hostname, path="/")

    def pre_save(self, *args, **kwargs):
        if self.key:
            return
        pk = asyncssh.generate_private_key("ssh-rsa", comment=self.name)
        # For compatibility with older SSH implementations
        self.key = pk.export_private_key("pkcs1-pem")
        self.save()

    def post_save(self, *args, **kwargs):
        if not self.online:
            return
        if self.provision:
            from .tasks import EpiphanTasks

            EpiphanTasks.provision.apply_async(
                (self.pk,), queue=settings.VIDEO_CELERY_QUEUE
            )

    def reboot(self):
        url = self.url.path("admin/reboot.cgi").as_string()
        logger.info("Requesting reboot: {}".format(url))
        self.session.get(url)
        self.online = False
        self.save()

    @property
    def status(self):
        url = self.url.path("api/system/status").as_string()
        return self.session.get(url).json().get("result")

    @property
    def firmware(self):
        url = self.url.path("api/system/firmware").as_string()
        return self.session.get(url).json().get("result")

    @property
    def hardware(self):
        url = self.url.path("api/system/hardware").as_string()
        return self.session.get(url).json().get("result")


@signal_connect
class EpiphanChannel(models.Model):
    epiphan = models.ForeignKey("Epiphan", on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    path = models.CharField(max_length=10)
    sizelimit = models.CharField(
        max_length=16,
        default="1GiB",
        validators=[
            RegexValidator(
                regex=re.compile(r"^\d+(?:[kmgtpe]i?b?)?$", re.IGNORECASE),
                message=_("Size limit must be an integer followed by a SI unit"),
                code="no_filesize",
            )
        ],
    )
    timelimit = models.DurationField(default=timedelta(hours=3))

    class Meta:
        ordering = ("name",)

    def request(self, key, value=None):
        m = value and "set" or "get"
        path = "admin/{s.path}/{m}_params.cgi".format(s=self, m=m)
        url = self.epiphan.url.path(path).query_param(key, value).as_string()
        try:
            r = self.epiphan.session.get(url)
        except Exception as e:
            logger.warn(e)
            return None
        else:
            delete_memoized(self.recording)
            return r

    def start(self):
        if self.recording():
            return
        logger.info("Starting recording for {s}".format(s=self))
        self.request("rec_enabled", "on")

    def stop(self):
        if not self.recording():
            return
        logger.info("Stopping recording for {s}".format(s=self))
        self.request("rec_enabled", "off")

    @memoize(timeout=10)
    def recording(self):
        if not self.epiphan.online:
            return False
        r = self.request("rec_enabled", "")
        if not r:
            return False
        return re.match("^rec_enabled = on$", r.text) is not None

    def response(self):
        data = dict()
        data["recording"] = self.recording()
        return data

    def __str__(self):
        return "{s.epiphan}, {s.name}".format(s=self)

    def __repr__(self):
        return "{s.__class__.__name__}({s.pk})".format(s=self)


@signal_connect
class EpiphanSource(models.Model):
    epiphan = models.ForeignKey("Epiphan", on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    url = models.URLField(null=True)
    number = models.PositiveSmallIntegerField()
    port = models.PositiveIntegerField(default=554)
    input = models.ForeignKey("Input", blank=True, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ("epiphan__room__campusonline__name_short", "number")

    @property
    def rtsp(self):
        return f"rtsp://{self.epiphan.hostname}:{self.port}/stream.sdp"

    def generate_preview(self):
        logger.debug(f"{self}: Generating previews from {self.url}")
        try:
            inp = subprocess.Popen(
                ["ffmpeg", "-t", "5", "-i", self.url, "-f", "mpegts", "-"],
                stdout=subprocess.PIPE,
            )
            video = subprocess.Popen(
                [
                    "ffmpeg",
                    "-f",
                    "mpegts",
                    "-i",
                    "pipe:",
                    "-vcodec",
                    "libwebp",
                    "-frames:v",
                    "1",
                    "-f",
                    "image2pipe",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
            audio = subprocess.Popen(
                [
                    "ffmpeg",
                    "-f",
                    "mpegts",
                    "-i",
                    "pipe:",
                    "-filter_complex",
                    "showwavespic=s=1280x240:colors=#51AE32",
                    "-vcodec",
                    "libwebp",
                    "-frames:v",
                    "1",
                    "-f",
                    "image2pipe",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
            while (data := inp.stdout.read(8192)):
                video.stdin.write(data)
                audio.stdin.write(data)
            video.stdin.close()
            audio.stdin.close()
            logger.debug(f"{self}: Saving new preview image")
            cache.set(
                f"EpiphanSource-{self.id}-video-preview", video.stdout.read(), 120
            )
            logger.debug(f"{self}: Saving new waveform image")
            cache.set(
                f"EpiphanSource-{self.id}-audio-waveform",
                audio.stdout.read(),
                120,
            )
            inp.wait()
            video.wait()
            audio.wait()
        except Exception as e:
            logger.warn(f"{self}: Failed to generate previews: {e}")
            cache.delete(f"EpiphanSource-{self.id}-video-preview")
            cache.delete(f"EpiphanSource-{self.id}-audio-waveform")

    @property
    def video_preview(self):
        data = cache.get(f"EpiphanSource-{self.id}-video-preview")
        if not data:
            name = finders.find("video/placeholder/video.webp")
            with open(name, "rb") as f:
                data = f.read()
        b64 = b64encode(data).decode()
        return f"data:image/webp;base64,{b64}"

    @property
    def audio_waveform(self):
        data = cache.get(f"EpiphanSource-{self.id}-audio-waveform")
        if not data:
            name = finders.find("video/placeholder/audio.webp")
            with open(name, "rb") as f:
                data = f.read()
        b64 = b64encode(data).decode()
        return f"data:image/webp;base64,{b64}"

    def __str__(self):
        return "{s.epiphan}, {s.number}".format(s=self)


@signal_connect
class EpiphanInput(models.Model):
    epiphan = models.ForeignKey("Epiphan", on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    nosignal_src = models.ForeignKey(
        "EpiphanMedia", on_delete=models.CASCADE, null=True, blank=True
    )
    nosignal_timeout = models.PositiveSmallIntegerField(null=True, blank=True)
    deinterlacing = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    def post_save(self, *args, **kwargs):
        from .tasks import EpiphanInputTasks

        if self.nosignal_src:
            EpiphanInputTasks().set.apply_async(
                (self.pk,), queue=settings.VIDEO_CELERY_QUEUE
            )
        else:
            EpiphanInputTasks().unset.apply_async(
                (self.epiphan.pk, self.name), queue=settings.VIDEO_CELERY_QUEUE
            )

    def pre_delete(self, *args, **kwargs):
        if self.nosignal_src:
            from .tasks import EpiphanInputTasks

            EpiphanInputTasks().unset.apply_async(
                (self.epiphan.pk, self.name), queue=settings.VIDEO_CELERY_QUEUE
            )


@signal_connect
class EpiphanMedia(models.Model):
    epiphan = models.ForeignKey("Epiphan", on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    image = models.ImageField(
        upload_to=Uuid4Upload,
    )

    def __str__(self):
        return self.name

    def pre_save(self, *args, **kwargs):
        self.name = self.image.name

    def post_save(self, *args, **kwargs):
        from .tasks import EpiphanMediaTasks

        EpiphanMediaTasks().upload.apply_async(
            (self.pk,), queue=settings.VIDEO_CELERY_QUEUE
        )

    def pre_delete(self, *args, **kwargs):
        if self.image:
            from .tasks import EpiphanMediaTasks

            EpiphanMediaTasks().remove.apply_async(
                (self.epiphan.pk, self.name), queue=settings.VIDEO_CELERY_QUEUE
            )
            self.image.delete(False)


class Input(PolymorphicModel):
    name = models.CharField(max_length=128, blank=False, null=False)


class PanasonicCamera(NetworkedDeviceMixin, Input):
    pass


@signal_connect
class Recording(
    ExportModelOperationsMixin("video.Recording"), TimeStampedModel, PolymorphicModel
):
    recorder = models.ForeignKey(
        "Recorder", null=True, blank=True, on_delete=models.SET_NULL
    )
    online = models.FileField(upload_to=Uuid4Upload, null=True)
    info = JSONField(null=True)
    archive = models.FileField(
        upload_to=Uuid4Upload,
        default=None,
        null=True,
        blank=True,
        storage=FileSystemStorage(location="/archive"),
    )
    start = models.DateTimeField(null=True)
    course = models.ForeignKey(
        "campusonline.Course",
        on_delete=models.SET_NULL,
        db_constraint=False,
        null=True,
        blank=True,
        related_name="+",
    )
    presenter = models.ForeignKey(
        "campusonline.Person",
        on_delete=models.SET_NULL,
        db_constraint=False,
        null=True,
        blank=True,
        related_name="+",
    )
    title = models.TextField(blank=True, null=True)
    metadata = JSONField(blank=True, null=True)
    ready = models.BooleanField(default=False)

    @property
    def end(self):
        if not self.start:
            return None
        try:
            duration = float(self.info["format"]["duration"])
            return self.start + timedelta(seconds=duration)
        except KeyError as e:
            logger.warn(e)
            return None

    class Meta:
        ordering = ("-created",)

    def pre_delete(self, *args, **kwargs):
        if self.online:
            self.online.delete(False)
        if self.archive:
            self.archive.delete(False)

    def __str__(self):
        return "Recorded by {s.recorder} on {s.modified}".format(s=self)


class EpiphanRecording(Recording):
    channel = models.ForeignKey(
        "EpiphanChannel", null=True, blank=True, on_delete=models.SET_NULL
    )


@signal_connect
class RecordingAsset(TimeStampedModel):
    recording = models.ForeignKey("Recording", on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    data = models.FileField(upload_to=Uuid4Upload)
    mimetype = models.TextField()
    preview = ProcessedImageField(
        upload_to=Uuid4Upload,
        processors=[ResizeToFill(500, 50)],
        format="JPEG",
        options={"quality": 60},
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-created",)

    def __str__(self):
        return self.name

    def pre_delete(self, *args, **kwargs):
        self.data.delete(False)
        self.preview.delete(False)


class Export(
    ExportModelOperationsMixin("video.Export"), TimeStampedModel, PolymorphicModel
):
    recording = models.ForeignKey("Recording", on_delete=models.CASCADE)


@signal_connect
class SideBySideExport(Export):
    data = models.FileField(upload_to=Uuid4Upload)

    class Meta:
        verbose_name = "Side-by-Side"

    def process(self, notify):
        streams = self.recording.info["streams"]
        vis = [s for s in streams if s["codec_type"] == "video"]
        height = max([v["coded_height"] for v in vis])
        videos = []
        for i, v in enumerate(vis):
            if v["coded_height"] < height:
                filt = "pad=height={}".format(height)
            else:
                filt = "null"
            videos.append(("[i:{}]{}[v{}]".format(v["id"], filt, i), "[v{}]".format(i)))
        aus = [s for s in streams if s["codec_type"] == "audio"]
        fc = "{vf};{v}hstack=inputs={vl}[v];{a}amerge[a]".format(
            vf=";".join([v[0] for v in videos]),
            v="".join([v[1] for v in videos]),
            vl=len(videos),
            a="".join(["[i:{}]".format(a["id"]) for a in aus]),
        )
        with NamedTemporaryFile(suffix=".mp4") as output:
            args = [
                "ffmpeg",
                "-y",
                "-i",
                self.recording.online.path,
                "-filter_complex",
                fc,
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-ac",
                "2",
                output.name,
            ]
            ffmpeg = Process(*args)
            ffmpeg.handler(FFMPEGProgressHandler(partial(notify, "Stitching")))
            ffmpeg.run()
            self.data.save(output.name, File(output.file))

    def pre_delete(self, *args, **kwargs):
        self.data.delete(False)


@signal_connect
class ZipStreamExport(Export):
    data = models.FileField(upload_to=Uuid4Upload)

    class Meta:
        verbose_name = "Zip-Stream"

    def process(self, notify):
        if "streams" not in self.recording.info:
            from .tasks import RecordingTasks

            RecordingTasks.process.run(self.pk)
        mapping = {"h264": "m4v", "aac": "m4a"}
        streams = []
        args = ["ffmpeg", "-y", "-i", self.recording.online.path]
        with TemporaryDirectory(prefix="recording") as path:
            for s in self.recording.info["streams"]:
                f = mapping.get(s["codec_name"])
                name = os.path.join(
                    path, "{s[codec_type]}-{s[id]}.{f}".format(s=s, f=f)
                )
                args.extend(["-map", "i:{s[id]}".format(s=s), "-c", "copy", name])
                streams.append(name)
            ffmpeg = Process(*args)
            ffmpeg.handler(FFMPEGProgressHandler(partial(notify, "Splitting")))
            ffmpeg.run()
            with NamedTemporaryFile(suffix=".zip") as output:
                with ZipFile(output, "w") as arc:
                    for i, f in enumerate(streams):
                        notify("Zipping", i + 1, len(streams))
                        arc.write(f, os.path.basename(f))
                        os.remove(f)
                self.data.save(output.name, File(output.file))

    def pre_delete(self, *args, **kwargs):
        self.data.delete(False)


class TranscribeLanguage(OrderedModel):
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=32)

    class Meta(OrderedModel.Meta):
        pass

    def __str__(self):
        return f"{self.name} ({self.code})"


class LivePortal(models.Model):
    name = models.CharField(max_length=512)
    control = models.URLField()
    username = models.CharField(max_length=128, null=True, blank=True)
    password = models.CharField(max_length=128, null=True, blank=True)
    timeout = models.PositiveSmallIntegerField(default=5)

    def __str__(self):
        return self.name

    @property
    def auth(self):
        if self.username and self.password:
            return requests.auth.HTTPBasicAuth(self.username, self.password)

    def start(self, event, request=None):
        payload = {
            "id": event.channel.pk,
            "viewer": event.viewer(request),
            "title": event.title,
            "description": event.description.rendered,
            "unrestricted": event.public,
            "previews": event.previews(),
        }
        try:
            resp = requests.put(
                self.control, json=payload, auth=self.auth, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to notify {self} of event {event} start: {e}")

    def stop(self, event):
        payload = {"id": event.channel.pk}
        try:
            resp = requests.delete(
                self.control, json=payload, auth=self.auth, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to notify {self} of event {event} start: {e}")


class LiveChannel(OrderedModel):
    id = ShortUUIDField(primary_key=True)
    name = models.CharField(max_length=512)
    enabled = models.BooleanField(default=False)
    portals = models.ManyToManyField(LivePortal)

    def __str__(self):
        return self.name


@signal_connect
class LiveDeliveryServer(models.Model):
    base = models.URLField()
    config = models.CharField(max_length=256, validators=[RedisURLValidator()])
    online = models.BooleanField(default=False, editable=False)
    enabled = models.BooleanField(default=False)
    timeout = models.PositiveSmallIntegerField(default=5)

    def __str__(self):
        return self.base

    def is_alive(self):
        try:
            requests.get(self.base, timeout=self.timeout).raise_for_status()
        except requests.exceptions.RequestException:
            return False
        return True

    def pre_save(self, *args, **kwargs):
        self.online = self.is_alive()

    @property
    @lru_cache()
    def redis(self):
        url = URL(self.config)
        if url.scheme() == "unix":
            return Redis(unix_socket_path=url.path())
        if url.scheme() == "redis":
            return Redis(
                host=url.host(), port=url.port(), db=int(url.query_param("db") or 0)
            )
        if url.scheme() == "redis+tls":
            return Redis(
                host=url.host(),
                port=url.port(),
                db=int(url.query_param("db") or 0),
                ssl=True,
                ssl_ca_certs=certifi.where(),
            )
        raise Exception(f"{self.config} is not a valid Redis URL")


class LiveDeliveryServerCountry(models.Model):
    server = models.ForeignKey(LiveDeliveryServer, on_delete=models.CASCADE)
    country = CountryField()

    def __str__(self):
        return self.country.name


class LiveDeliveryServerNetwork(models.Model):
    server = models.ForeignKey(LiveDeliveryServer, on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    inet = CidrAddressField()

    objects = NetManager()

    def __str__(self):
        return self.name


class LiveEvent(ExportModelOperationsMixin("video.LiveEvent"), models.Model):
    id = ShortUUIDField(primary_key=True)
    channel = models.ForeignKey(LiveChannel, on_delete=models.CASCADE)
    public = models.BooleanField(default=False)
    started = models.DateTimeField(null=True, editable=False)
    begin = models.DateTimeField(null=True, editable=False)
    end = models.DateTimeField(null=True, editable=False)
    title = models.CharField(max_length=512)
    description = MarkupField(default_markup_type="markdown")
    delivery = models.ManyToManyField(LiveDeliveryServer)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, null=True, editable=False)

    @property
    def script(self):
        return get_template("video/live/event.script").template.source

    def start(self):
        from .tasks import LiveEventTasks

        self.started = timezone.now()
        self.save()
        for le in LiveEvent.objects.filter(end=None, channel=self.channel).exclude(
            pk=self.pk
        ):
            logger.warning(f"Stopping active LiveEvent {le} ahead of starting {self}")
            le.stop()
        if not self.job:
            self.job = Job.objects.create(script=self.script)
            requirements = self.livestream_set.values_list(
                "variants__livestreamvariantrequirement__resource",
                "variants__livestreamvariantrequirement__slots",
            )
            required = sum(
                [Counter({Resource.objects.get(pk=r): s}) for r, s in requirements],
                Counter(),
            )
            for r, c in required.items():
                JobConstraint.objects.create(job=self.job, resource=r, required=c)
            if not self.job.assign():
                logger.error(f"Could not assign job for {self}")
                return False
        if not self.job.running:
            if not self.job.start({"event": self}):
                logger.error(f"Could not start job for {self}")
                return False
        # Set transcoder id on delivery servers
        for ds in self.delivery.all():
            ds.redis.set(
                f"HLS/Event/{self.pk}", self.job.worker.properties.get("transcoder-id")
            )
        # transaction.commit()
        # task = LiveEventTasks.ready_to_publish.apply_async(
        #    (self.pk,),
        #    queue=settings.VIDEO_CELERY_QUEUE
        # )
        # task.wait(60)
        retry = Retrying(
            stop=stop_after_attempt(settings.VIDEO_LIVE_STARTUP_ATTEMPTS),
            wait=wait_fixed(settings.VIDEO_LIVE_STARTUP_WAIT),
        )
        try:
            for attempt in retry:
                with attempt:
                    for ds in self.delivery.all():
                        v = LiveViewer.objects.create(event=self, delivery=ds)
                        try:
                            for ls in self.livestream_set.all():
                                url = ls.viewer(viewer=v)
                                streamlink.streams(url)
                        except streamlink.StreamlinkError as e:
                            logger.warn(
                                f"Stream {ls} not ready after {attempt.retry_state.attempt_number}: {e}"
                            )
                            raise e
                        finally:
                            v.disable()
                            v.delete()
        except RetryError:
            logger.error(f"Could not find initialized streams for: {self}")
            self.job.stop()
            return False
        # Notify portal
        for portal in self.channel.portals.all():
            portal.start(self)
        self.begin = timezone.now()
        self.save()
        return True

    def stop(self):
        from .tasks import LiveEventTasks

        self.end = timezone.now()
        # Notify portal
        for portal in self.channel.portals.all():
            portal.stop(self)
        # Remove transcoder id from delivery servers
        for ds in self.delivery.all():
            ds.redis.delete(f"HLS/Event/{self.pk}")
        # Stop transcoding job
        if self.job:
            try:
                self.job.stop()
            except Exception:
                logger.warn(f"Could not stop job for {self}")
        self.save()
        transaction.on_commit(
            lambda: LiveEventTasks.cleanup.apply_async(
                (self.pk,), queue=settings.VIDEO_CELERY_QUEUE
            )
        )

    def viewer(self, request):
        path = reverse("video:live-viewer", kwargs={"event_id": self.pk})
        if request:
            return request.build_absolute_uri(path)
        return URL(
            scheme="https", host=Site.objects.get_current().domain, path=path
        ).as_string()

    def previews(self):
        data = dict()
        for s in self.livestream_set.all():
            data[s.type] = list()
            for d in self.delivery.all():
                url = (
                    URL(d.base)
                    .add_path_segment(self.pk)
                    .add_path_segment(f"{s.pk}.jpg")
                )
                data.get(s.type).append(url.as_string())
        return data

    def viewer_count(self):
        return max([s.viewer_count() for s in self.livestream_set.all()])

    def excel(self, output):
        wb = Workbook()
        wb.active.title = str(self.title)
        wb.active.append(
            (
                ugettext("Viewer-ID"),
                ugettext("Delivery-URL"),
                ugettext("Stream Type"),
                ugettext("Timestamp"),
                ugettext("Variant"),
            )
        )
        for lv in self.liveviewer_set.all():
            for sid, timestamps in lv.statistics.items():
                ls = self.livestream_set.get(pk=sid)
                for ts, variant in timestamps.items():
                    wb.active.append(
                        (
                            lv.pk,
                            str(lv.delivery),
                            ls.type,
                            ts,
                            variant,
                        )
                    )
        archive = ZipFile(output, "w", ZIP_DEFLATED, allowZip64=True)
        writer = ExcelWriter(wb, archive)
        writer.save()
        return wb.mime_type

    def __str__(self):
        return f"{self.pk}: {self.title}"


class LiveStreamVariant(models.Model):
    height = models.PositiveSmallIntegerField()
    preset = models.CharField(max_length=32)
    profile = models.CharField(max_length=32)
    video = models.CharField(
        max_length=16,
        # validators=[
        #    UnitValidator("byte")
        # ],
    )
    audio = models.CharField(
        max_length=16,
        # validators=[
        #    UnitValidator("byte")
        # ],
    )

    def __str__(self):
        return f"{self.height}@{self.video}"


class LiveStreamVariantRequirement(models.Model):
    variant = models.ForeignKey(LiveStreamVariant, on_delete=models.CASCADE)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
    slots = models.PositiveIntegerField()


@signal_connect
class LiveViewer(ExportModelOperationsMixin("video.LiveViewer"), models.Model):
    id = ShortUUIDField(primary_key=True)
    event = models.ForeignKey(LiveEvent, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    delivery = models.ForeignKey(LiveDeliveryServer, on_delete=models.CASCADE)
    client = InetAddressField(blank=True, null=True)
    statistics = JSONField(null=True, blank=True)

    objects = NetManager()

    def get_country(self):
        if not self.client:
            return
        try:
            geoip = settings.VIDEO_GEOIP_DATABASE.city(self.client)
        except Exception:
            return
        return geoip.country.iso_code

    def get_server(self):
        server = getattr(self, "delivery", None)
        if server:
            return server
        if self.client:
            server = (
                LiveDeliveryServer.objects.filter(
                    livedeliveryservernetwork__inet__net_contains=self.client,
                    online=True,
                    enabled=True,
                )
                .order_by("?")
                .first()
            )
            if server:
                return server
            country = self.get_country()
            if country:
                server = (
                    LiveDeliveryServer.objects.filter(
                        livedeliveryservercountry__country=country,
                        online=True,
                        enabled=True,
                    )
                    .order_by("?")
                    .first()
                )
                if server:
                    return server
        server = (
            LiveDeliveryServer.objects.filter(
                livedeliveryservernetwork__inet__isnull=True,
                livedeliveryservercountry__country__isnull=True,
                online=True,
                enabled=True,
            )
            .order_by("?")
            .first()
        )
        return server

    def pre_save(self, *args, **kwargs):
        if hasattr(self, "delivery"):
            return
        server = self.get_server()
        if not server:
            raise LiveDeliveryServer.DoesNotExist()
        self.delivery = server

    def post_save(self, *args, **kwargs):
        if not self.event.end:
            self.delivery.redis.setex(
                f"HLS/Viewer/{self.pk}",
                settings.VIDEO_LIVE_VIEWER_LIFETIME,
                self.event.pk,
            )

    def disable(self):
        self.delivery.redis.delete(f"HLS/Viewer/{self.pk}")

    def collect(self):
        fmt = settings.VIDEO_LIVE_DELIVERY_NOW_FORMAT
        tz = settings.VIDEO_LIVE_DELIVERY_NOW_TIMEZONE
        strp = timezone.datetime.strptime
        self.statistics = {
            s.pk: {
                strp(ts.decode(), fmt)
                .replace(tzinfo=tz)
                .isoformat(): str(s.variants.all()[int(sid.decode())])
                for ts, sid in self.delivery.redis.hgetall(
                    f"HLS/Viewer/{self.pk}/{s.pk}"
                ).items()
            }
            for s in self.event.livestream_set.prefetch_related("variants").all()
        }

    def cleanup(self):
        self.delivery.redis.delete(f"HLS/Viewer/{self.pk}")
        for s in self.event.streams.all():
            self.delivery.redis.delete(f"HLS/Viewer/{self.pk}/{s.pk}")

    def __str__(self):
        return f"{self.event}: {self.id} ({self.delivery})"


class LiveStream(models.Model):
    id = ShortUUIDField(primary_key=True)
    event = models.ForeignKey(LiveEvent, on_delete=models.CASCADE)
    type = models.CharField(max_length=128)
    source = models.CharField(max_length=512)
    variants = models.ManyToManyField(LiveStreamVariant)
    list_size = models.PositiveIntegerField()
    delete_threshold = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.event}: {self.type}"

    def viewer(self, viewer: LiveViewer):
        url = reduce(
            lambda u, s: u.add_path_segment(s),
            (viewer.event.pk, viewer.pk, f"{self.pk}.m3u8"),
            URL(viewer.delivery.base),
        )
        return url.as_string()

    def stats(self):
        accumulator = dict()
        for delivery in self.event.delivery.filter(online=True):
            timestamps = delivery.redis.hgetall(f"HLS/Stream/{self.event.pk}/{self.pk}")
            for t, c in timestamps.items():
                accumulator[t] = accumulator.get(t, 0) + int(c)
        LiveStreamStatistic.objects.bulk_create(
            [
                LiveStreamStatistic(stream=self, datetime=t, viewers=c)
                for t, c in accumulator.items()
            ]
        )

    @memoize(timeout=30)
    def viewer_count(self):
        now = (
            timezone.now()
            .astimezone(settings.VIDEO_LIVE_DELIVERY_NOW_TIMEZONE)
            .strftime(settings.VIDEO_LIVE_DELIVERY_NOW_FORMAT)
        )
        return sum(
            [
                d.redis.hget(f"HLS/Stream/{self.event.pk}/{self.pk}", now) or 0
                for d in self.event.delivery.filter(online=True)
            ]
        )

    def cleanup(self):
        for delivery in self.event.delivery.filter(online=True):
            delivery.redis.delete(f"HLS/Stream/{self.event.pk}/{self.pk}")


class LiveStreamStatistic(models.Model):
    stream = models.ForeignKey(LiveStream, on_delete=models.CASCADE)
    datetime = models.DateTimeField()
    viewers = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.stream}@{self.datetime}"


class LiveTemplate(models.Model):
    name = models.CharField(max_length=128)
    room = models.ForeignKey(
        "campusonline.Room",
        on_delete=models.SET_NULL,
        db_constraint=False,
        null=True,
        blank=True,
        related_name="+",
    )
    channel = models.ForeignKey(LiveChannel, on_delete=models.CASCADE)
    title = models.CharField(max_length=512)
    description = models.TextField()
    delivery = models.ManyToManyField(LiveDeliveryServer)

    def __str__(self):
        return f"{self.name} ({self.room})"


class LiveTemplateScene(models.Model):
    template = models.ForeignKey(LiveTemplate, on_delete=models.CASCADE)
    name = models.CharField(max_length=128)

    def __str__(self):
        return f"{self.template}: {self.name}"

    def instantiate(self, public=True):
        context = Context({"scene": self, "campusonline": None})
        if self.template.room:
            from outpost.django.campusonline.serializers import (
                CourseSerializer,
                PersonSerializer,
            )

            cgt = (
                CourseGroupTerm.objects.filter(
                    room=self.template.room,
                    start__lte=timezone.now() + timedelta(minutes=30),
                    end__gte=timezone.now(),
                )
                .values("start", "end", "person", "title", "coursegroup__course")
                .distinct()
                .first()
            )
            if not cgt:
                logger.warn("No Course Group Term found")
            else:
                try:
                    course = Course.objects.get(pk=cgt.get("coursegroup__course"))
                except Course.DoesNotExists as e:
                    logger.warn(f"No Course found: {e}")
                    course = None
                try:
                    presenter = Person.objects.get(pk=cgt.get("person"))
                except Person.DoesNotExist as e:
                    logger.warn(f"No Person found: {e}")
                    presenter = None
                context["campusonline"] = {
                    "title": cgt.get("title", ""),
                    "presenter": PersonSerializer(presenter).data
                    if presenter
                    else None,
                    "course": CourseSerializer(course).data if course else None,
                }
        event = LiveEvent.objects.create(
            channel=self.template.channel,
            public=public,
            title=Template(self.template.title).render(context),
            description=Template(self.template.description).render(context),
        )
        for d in self.template.delivery.all():
            event.delivery.add(d)
        for ts in self.livetemplatestream_set.all():
            stream = LiveStream.objects.create(
                type=ts.type,
                event=event,
                source=ts.source.url,
                list_size=ts.list_size,
                delete_threshold=ts.delete_threshold,
            )
            for tv in ts.variants.all():
                stream.variants.add(tv)
        return event


class LiveTemplateStream(models.Model):
    scene = models.ForeignKey(LiveTemplateScene, on_delete=models.CASCADE)
    type = models.CharField(max_length=128)
    source = models.ForeignKey(EpiphanSource, on_delete=models.CASCADE)
    variants = models.ManyToManyField(LiveStreamVariant)
    list_size = models.PositiveIntegerField()
    delete_threshold = models.PositiveIntegerField()


# class Transcription(models.Model):
#    event = models.ForeignKey("Event)")
#    language = models.ForeignKey("TranscribeLanguage")
#    created = models.DateTimeField(auto_now_add=True)
#    data = JSONField(blank=True, null=True)
#    duration = models.DurationField()
#
#    @staticmethod
#    def timestamp(sec: float) -> str:
#        t = relativedelta(microseconds=int(sec * (10 ** 6)))
#        return f"{t.hours:03.0f}:{t.minutes:02.0f}:{t.seconds:02.0f}.{t.microseconds/1000:03.0f}"
#
#    @staticmethod
#    def content(a, v) -> str:
#        c = max(v.get("alternatives"), key=lambda k: float(k.get("confidence"))).get(
#            "content"
#        )
#        if not a:
#            return c
#        if v.get("type") == "punctuation":
#            return f"{a}{c}"
#        return f"{a} {c}"
#
#    @property
#    def vtt(self):
#        items = self.data.get("results").get("items")
#        sentences = split_after(items, lambda i: i.get("type") == "punctuation")
#        vtt = WebVTT()
#        for s in sentences:
#            csize = ceil(len(s) / 12)
#            for p in divide(csize, s):
#                lst = list(p)
#                text = reduce(self.content, lst, None)
#                pro = list(filter(lambda i: i.get("type") == "pronunciation", lst))
#                start = self.timestamp(
#                    min(map(lambda i: float(i.get("start_time")), pro))
#                )
#                end = self.timestamp(max(map(lambda i: float(i.get("end_time")), pro)))
#                caption = Caption(start, end, map(" ".join, divide(2, text.split())))
#                vtt.captions.append(caption)
#        output = io.StringIO()
#        vtt.write(output)
#        return output.getvalue()
#
#    @property
#    def text(self) -> str:
#        tr = self.data.get("results").get("transcripts")
#        return "".join([t.get("transcript") for t in tr])
