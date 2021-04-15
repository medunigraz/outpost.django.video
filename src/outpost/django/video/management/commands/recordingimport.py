import argparse
import logging
import re
from pathlib import Path

from django.core.files.base import File
from django.core.management.base import BaseCommand

from ...models import Epiphan, EpiphanChannel, EpiphanRecording
from ...tasks import RecordingTasks

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Runs the video upload SFTP server."
    pattern = re.compile(
        r"^(?P<stream>[\w]+)_(?P<created>\w{3}\d{2}_\d{2}-\d{2}-\d{2})\.(?P<extension>\w+)$"
    )

    def add_arguments(self, parser):
        parser.add_argument("-e", type=int, dest="epiphan")
        parser.add_argument("recording", type=argparse.FileType("rb"), nargs="+")

    def handle(self, *args, **options):
        epiphan = Epiphan.objects.get(pk=options["epiphan"])
        for r in options["recording"]:
            path = Path(r.name)
            logger.info("Importing recording: {}".format(path.name))
            matches = self.pattern.match(path.name)
            if not matches:
                logger.warn("Could not parse file name: {}".format(path.name))
                continue
            channel = None
            try:
                stream = matches.groupdict().get("stream")
                if stream:
                    channel = EpiphanChannel.objects.get(epiphan=epiphan, name=stream)
            except EpiphanChannel.DoesNotExist:
                logger.warn("Could not find Epiphan channel {}".format(stream))
                continue
            rec = EpiphanRecording(recorder=epiphan, channel=channel)
            rec.data.save(path.name, File(r))
            RecordingTask.process.delay(rec.pk)
