from imagekit import (
    ImageSpec,
    register,
)
from imagekit.processors import ResizeToFit


class SourceThumbnail(ImageSpec):
    processors = [ResizeToFit(600, 600)]
    format = "JPEG"
    options = {"quality": 60}


register.generator("video:source_thumbnail", SourceThumbnail)
