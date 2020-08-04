import io
import logging
import os
import re
import subprocess
import django
from base64 import b64encode
from datetime import timedelta
from functools import partial, reduce
from hashlib import sha256
from math import ceil
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZipFile

import asyncssh
import requests
from dateutil.relativedelta import relativedelta
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.postgres.fields import JSONField
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django_extensions.db.models import TimeStampedModel
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill
from memoize import delete_memoized, memoize
from more_itertools import chunked, divide, split_after
from ordered_model.models import OrderedModel
from outpost.django.base.decorators import signal_connect
from outpost.django.base.models import NetworkedDeviceMixin
from outpost.django.base.utils import Process, Uuid4Upload
from PIL import Image
from polymorphic.models import PolymorphicModel
from purl import URL
from webvtt import Caption, WebVTT

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
        cache.set("outpost-video-server-{}".format(str(self)), True, timeout=10)

    @property
    def active(self):
        return cache.get("outpost-video-server-{}".format(str(self)), False)

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
        permissions = (
            (("view_recorder", _("View Recorder")),)
            if django.VERSION < (2, 1)
            else tuple()
        )

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
        d = sha256(k.get_ssh_public_key()).digest()
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
            from .tasks import EpiphanProvisionTask

            EpiphanProvisionTask().run(self.pk)

    def reboot(self):
        url = self.url.path("admin/reboot.cgi").as_string()
        logger.info("Requesting reboot: {}".format(url))
        self.session.get(url)
        self.online = False
        self.save()


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
    number = models.PositiveSmallIntegerField()
    port = models.PositiveIntegerField(default=554)
    input = models.ForeignKey("Input", blank=True, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ("number",)

    @property
    def rtsp(self):
        return f"rtsp://{self.epiphan.hostname}:{self.port}/stream.sdp"

    def generate_video_preview(self):
        # Video preview
        logger.debug(f"{self}: Fetching video preview from {self.rtsp}")
        try:
            args = [
                "ffmpeg",
                "-y",
                "-stimeout",
                "200000",
                "-i",
                self.rtsp,
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-",
            ]
            ffmpeg = subprocess.run(
                args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True
            )
            img = Image.open(io.BytesIO(ffmpeg.stdout))
            buf = io.BytesIO()
            img.save(buf, "JPEG", optimize=True, quality=70)
            logger.debug(f"{self}: Saving new preview image")
            cache.set(
                f"EpiphanSource-{self.id}-video-preview", buf.getbuffer().tobytes(), 120
            )
        except Exception as e:
            logger.warn(f"{self}: Failed to generate video preview: {e}")
            cache.delete(f"EpiphanSource-{self.id}-video-preview")

    @property
    def video_preview(self):
        data = cache.get(f"EpiphanSource-{self.id}-video-preview")
        if not data:
            name = finders.find("video/placeholder/video.jpg")
            with open(name, "rb") as f:
                data = f.read()
        b64 = b64encode(data).decode()
        return f"data:image/jpeg;base64,{b64}"

    def generate_audio_waveform(self):
        # Audio waveform
        logger.debug(f"{self}: Fetching audio waveform from {self.rtsp}")
        try:
            args = [
                "ffmpeg",
                "-y",
                "-stimeout",
                "200000",
                "-t",
                "5",
                "-i",
                self.rtsp,
                "-filter_complex",
                "showwavespic=s=1280x240:colors=#51AE32",
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-",
            ]
            ffmpeg = subprocess.run(
                args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True
            )
            img = Image.open(io.BytesIO(ffmpeg.stdout))
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=True, quality=70)
            logger.debug(f"{self}: Saving new waveform image")
            cache.set(
                f"EpiphanSource-{self.id}-audio-waveform",
                buf.getbuffer().tobytes(),
                120,
            )
        except Exception as e:
            logger.warn(f"{self}: Failed to generate audio waveform: {e}")
            cache.delete(f"EpiphanSource-{self.id}-audio-waveform")

    @property
    def audio_waveform(self):
        data = cache.get(f"EpiphanSource-{self.id}-audio-waveform")
        if not data:
            name = finders.find("video/placeholder/audio.png")
            with open(name, "rb") as f:
                data = f.read()
        b64 = b64encode(data).decode()
        return f"data:image/png;base64,{b64}"

    def __str__(self):
        return "{s.epiphan}, {s.number}".format(s=self)


class Input(PolymorphicModel):
    name = models.CharField(max_length=128, blank=False, null=False)


class PanasonicCamera(NetworkedDeviceMixin, Input):
    pass


@signal_connect
class Recording(TimeStampedModel, PolymorphicModel):
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
        permissions = (
            (("view_recording", _("View Recording")),)
            if django.VERSION < (2, 1)
            else tuple()
        )

    def pre_delete(self, *args, **kwargs):
        if self.online:
            self.online.delete(False)
        if self.archive:
            self.archive.delete(False)

    def __str__(self):
        return "Recorded by {s.recorder} on {s.modified}".format(s=self)


class EpiphanRecording(Recording):
    channel = models.ForeignKey("EpiphanChannel", null=True, blank=True, on_delete=models.SET_NULL)


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
        permissions = (
            (("view_recordingasset", _("View Recording Asset")),)
            if django.VERSION < (2, 1)
            else tuple()
        )

    def __str__(self):
        return self.name

    def pre_delete(self, *args, **kwargs):
        self.data.delete(False)
        self.preview.delete(False)


class Export(TimeStampedModel, PolymorphicModel):
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
            from .tasks import ProcessRecordingTask

            ProcessRecordingTask().run(self.pk)
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


# class Opencast(models.Model):
#    url = models.URLField()
#    username = models.CharField(max_length=128)
#    password = models.CharField(max_length=128)
#    enabled = models.BooleanField(default=False)
#
#    def __str__(self):
#        return self.url
#
#
# class Event(models.Model):
#    opencast = models.ForeignKey("Opencast)")
#
#
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
