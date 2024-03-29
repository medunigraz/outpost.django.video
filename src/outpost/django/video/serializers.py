from outpost.django.api.serializers import Base64FileField
from outpost.django.campusonline.serializers import (
    CourseSerializer,
    PersonSerializer,
)
from outpost.django.geo.serializers import RoomSerializer
from rest_flex_fields import FlexFieldsModelSerializer
from rest_framework import serializers

from . import models


class ExportClassSerializer(serializers.BaseSerializer):
    id = serializers.CharField(max_length=256)
    name = serializers.CharField(max_length=256)

    def to_representation(self, cls):
        return {"id": cls[0], "name": cls[1]}


class RecorderSerializer(serializers.ModelSerializer):
    room = RoomSerializer()

    class Meta:
        model = models.Recorder
        fields = "__all__"


class EpiphanSerializer(RecorderSerializer):
    class Meta:
        model = models.Epiphan
        exclude = ("username", "password", "key")


class EpiphanChannelSerializer(serializers.ModelSerializer):
    recording = serializers.BooleanField()

    class Meta:
        model = models.EpiphanChannel
        fields = "__all__"


class EpiphanMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.EpiphanMedia
        fields = "__all__"


class EpiphanInputSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.EpiphanInput
        fields = "__all__"


class EpiphanSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.EpiphanSource
        fields = (
            "epiphan",
            "name",
            "number",
            "port",
            "rtsp",
            "video_preview",
            "audio_waveform",
        )
        read_only_fields = ("rtsp", "video_preview", "audio_waveform")


class RecordingSerializer(serializers.ModelSerializer):
    recorder = RecorderSerializer()
    course = CourseSerializer()
    presenter = PersonSerializer()
    end = serializers.DateTimeField()

    class Meta:
        model = models.Recording
        fields = (
            "id",
            "recorder",
            "course",
            "presenter",
            "created",
            "modified",
            "online",
            "info",
            "archive",
            "start",
            "end",
            "metadata",
            "title",
        )


class RecordingAssetSerializer(serializers.ModelSerializer):
    data = Base64FileField()

    class Meta:
        model = models.RecordingAsset
        fields = "__all__"


class LiveChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LiveChannel
        fields = ("id", "name", "portals")


class LiveTemplateSceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LiveTemplateScene
        fields = ("id", "name")


class LiveTemplateSerializer(FlexFieldsModelSerializer):
    class Meta:
        model = models.LiveTemplate
        fields = ("id", "name", "room", "livetemplatescene_set")

    expandable_fields = {
        "livetemplatescene_set": (
            LiveTemplateSceneSerializer,
            {"source": "livetemplatescene_set", "many": True},
        )
    }
