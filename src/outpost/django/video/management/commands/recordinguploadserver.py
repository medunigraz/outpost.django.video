import asyncio
import logging
import re
import sys
from datetime import datetime
from functools import partial, wraps
from pathlib import Path

import asyncssh
from celery import chain, group
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...conf import settings
from ...models import Epiphan, EpiphanChannel, EpiphanRecording, Server
from ...tasks import (
    AuphonicProcessTask,
    AuphonicResultTask,
    MetadataRecordingTask,
    NotifyRecordingTask,
    ProcessRecordingTask,
)

logger = logging.getLogger(__name__)


def log(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception("Exception in {}: {}".format(func.__name__, e))

    return wrapper


class SSHServer(asyncssh.SSHServer):
    def __init__(self, server):
        self._server = server

    def connection_made(self, conn):
        logger.debug("Got connection from {}".format(conn))
        self._conn = conn

    def begin_auth(self, username):
        logger.debug("User: {}".format(username))
        cond = {"pk": username, "server": self._server, "enabled": True}
        device = Epiphan.objects.get(**cond)
        logger.debug("Device: {}".format(device))
        private = asyncssh.import_private_key(device.key.tobytes())
        public = private.export_public_key().decode("ascii")
        logger.debug("Public key: {}".format(public))

        key = asyncssh.import_authorized_keys(public)

        self._conn.set_authorized_keys(key)
        return True

    def public_key_auth_supported(self):
        return True

    def password_auth_supported(self):
        return False

    def kbdint_auth_supported(self):
        return False


class SFTPServer(asyncssh.SFTPServer):

    pattern = re.compile(
        r"^(?P<stream>[\w]+)_(?P<created>\w{3}\d{2}_\d{2}-\d{2}-\d{2})\.(?P<extension>\w+)$"
    )

    def __init__(self, server, conn):
        username = conn.get_extra_info("username")
        self._server = server
        self._epiphan = Epiphan.objects.get(pk=username)
        super().__init__(conn)
        unsupported = [
            "read",
            "rename",
            "posix_rename",
            "remove",
            "readlink",
            "readlink",
            "link",
            "lstat",
            "fstat",
            "setstat",
            "fsetstat",
            "statvfs",
            "fstatvfs",
            "listdir",
            "mkdir",
            "rmdir",
        ]
        for f in unsupported:
            setattr(self, f, partial(self.unsupported, f))

    def format_user(self, uid):
        return str(self._epiphan.pk)

    def format_group(self, gid):
        return str(self._epiphan.pk)

    @log
    def open(self, raw, pflags, attrs):
        path = Path(raw.decode("utf-8"))
        logger.info("Uploading video: {}".format(path.name))
        matches = self.pattern.match(path.name)
        channel = None
        try:
            stream = matches.groupdict().get("stream")
            if stream:
                channel = EpiphanChannel.objects.get(epiphan=self._epiphan, name=stream)
        except EpiphanChannel.DoesNotExist:
            pass
        start = None
        try:
            now = timezone.now()
            created = matches.groupdict().get("created")
            start = timezone.make_aware(
                datetime.strptime(created, "%b%d_%H-%M-%S").replace(year=now.year)
            )
            if now < start:
                start = start.replace(start.year - 1)
            logger.debug(f"Determined start of recording: {start}")
        except Exception as e:
            logger.warn(e)
        rec = EpiphanRecording(
            recorder=self._epiphan, info={}, channel=channel, start=start, ready=False
        )
        rec.online.save(path.name, ContentFile(b""))
        if not rec.online.file.closed:
            rec.online.file.close()
        rec.online.file.open("wb")
        return rec

    @log
    def close(self, rec):
        logger.info("Finished file: {}".format(rec.online.path))
        if not rec.online.file.closed:
            rec.online.file.close()
        rec.ready = True
        rec.save()
        logger.info("Starting post-upload task chain")
        tasks = [ProcessRecordingTask().si(rec.pk), MetadataRecordingTask().si(rec.pk)]
        if rec.recorder.auphonic:
            tasks.extend(
                [AuphonicProcessTask().si(rec.pk), AuphonicResultTask().s(rec.pk)]
            )
        tasks.append(NotifyRecordingTask().si(rec.pk))
        result = chain(*tasks).delay()
        logger.info(f"Done starting post-upload task chain: {result.id}")

    @log
    def write(self, rec, offset, data):
        logger.debug("Writing {} bytes of data at offset {}".format(len(data), offset))
        rec.online.file.seek(offset)
        written = rec.online.file.write(data)
        logger.debug("Wrote {} bytes".format(written))
        return written

    def fstat(self, rec):
        now = int(datetime.timestamp(datetime.now()))
        return asyncssh.SFTPAttrs(
            size=rec.online.file.size,
            uid=0,
            gid=0,
            permissions=int("100600", 8),
            atime=now,
            mtime=now,
            nlink=1,
        )

    def stat(self, path):
        if path != b"/":
            raise asyncssh.SFTPError(asyncssh.FX_NO_SUCH_FILE, "no such file")
        now = int(datetime.timestamp(datetime.now()))
        return asyncssh.SFTPAttrs(
            size=216,
            uid=0,
            gid=0,
            permissions=int("40755", 8),
            atime=now,
            mtime=now,
            nlink=1,
        )

    def realpath(self, path):
        return b"/"

    def listdir(self, path):
        return [b".", b".."]

    def unsupported(self, n, *args):
        print(n, args)
        raise asyncssh.SFTPError(
            asyncssh.FX_OP_UNSUPPORTED, "This server supports upload only!"
        )


class Command(BaseCommand):
    help = "Runs the video upload SFTP server."

    def add_arguments(self, parser):
        parser.add_argument("server", nargs="*", type=int)

    def handle(self, *args, **options):

        loop = asyncio.get_event_loop()

        async def start_server(server):
            self.stdout.write(
                self.style.SUCCESS(
                    "Starting server on {s.hostname}:{s.port}".format(s=server)
                )
            )
            await asyncssh.create_server(
                host=server.hostname,
                port=server.port,
                server_factory=partial(SSHServer, server),
                sftp_factory=partial(SFTPServer, server),
                server_host_keys=[asyncssh.import_private_key(server.key.tobytes())],
                x11_forwarding=False,
                agent_forwarding=False,
                login_timeout=10,
                encryption_algs=settings.VIDEO_RECORDING_UPLOAD_SERVER_ENCRYPTION,
                mac_algs=settings.VIDEO_RECORDING_UPLOAD_SERVER_MAC,
            )
            while True:
                server.ping()
                await asyncio.sleep(5)

        cond = {"enabled": True}
        if options["server"]:
            cond["pk__in"] = options["server"]

        tasks = [start_server(s) for s in Server.objects.filter(**cond)]
        try:
            loop.run_until_complete(asyncio.gather(*tasks))
        except (OSError, asyncssh.Error) as exc:
            sys.exit("Error starting server: " + str(exc))
