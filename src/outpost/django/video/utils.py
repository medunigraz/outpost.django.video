import json
import logging
import math
import re
import subprocess
from functools import partial

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
