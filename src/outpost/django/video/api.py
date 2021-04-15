from django.http import Http404
from django.shortcuts import get_object_or_404
from guardian.shortcuts import get_objects_for_user
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from .permissions import EpiphanChannelPermissions
from .serializers import (
    EpiphanChannelSerializer,
    EpiphanSerializer,
    EpiphanSourceSerializer,
    ExportClassSerializer,
    RecorderSerializer,
    RecordingAssetSerializer,
    RecordingSerializer,
)
from .tasks import ExportTasks

from .models import (  # Broadcast,; EventAudio,; EventMedia,; EventVideo,; Publish,; Stream,; Token,
    Epiphan,
    EpiphanChannel,
    EpiphanSource,
    Export,
    Recorder,
    Recording,
    RecordingAsset,
)


class ExportClassViewSet(ListAPIView, RetrieveAPIView, GenericViewSet):
    serializer_class = ExportClassSerializer
    renderer_classes = [JSONRenderer]

    def get_queryset(self):
        classes = Export.__subclasses__()
        exporters = [(c.__name__, c._meta.verbose_name) for c in classes]
        return sorted(exporters, key=lambda x: x[0])

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        assert lookup_url_kwarg in self.kwargs, (
            "Expected view %s to be called with a URL keyword argument "
            'named "%s". Fix your URL conf, or set the `.lookup_field` '
            "attribute on the view correctly."
            % (self.__class__.__name__, lookup_url_kwarg)
        )

        exporter = self.kwargs[lookup_url_kwarg]
        exporters = dict(self.get_queryset())
        if exporter not in exporters:
            raise Http404("Unknown exporter: {}".format(exporter))
        return (exporter, exporters.get(exporter))

    def post(self, request, *args, **kwargs):
        exporter = request.data.get("exporter")
        recording = request.data.get("recording")
        task = ExportTasks.create.delay(recording, exporter, request.build_absolute_uri("/"))
        result = {"task": task.id}
        return Response(result)


class RecorderViewSet(ModelViewSet):
    queryset = Recorder.objects.all()
    serializer_class = RecorderSerializer
    permission_classes = (DjangoModelPermissions,)
    filter_fields = ()

    def get_queryset(self):
        return get_objects_for_user(
            self.request.user, "video.view_recorder", klass=self.queryset
        )


class RecordingViewSet(ModelViewSet):
    queryset = Recording.objects.all()
    serializer_class = RecordingSerializer
    permission_classes = (DjangoModelPermissions,)
    filter_fields = ("recorder",)

    def get_queryset(self):
        return get_objects_for_user(
            self.request.user, "video.view_recording", klass=self.queryset.model
        ).filter(ready=True)


class RecordingAssetViewSet(ModelViewSet):
    queryset = RecordingAsset.objects.all()
    serializer_class = RecordingAssetSerializer
    permission_classes = (DjangoModelPermissions,)
    filter_fields = ("recording", "mimetype")

    def get_queryset(self):
        return get_objects_for_user(
            self.request.user, "video.view_recordingasset", klass=self.queryset.model
        )


class EpiphanViewSet(ModelViewSet):
    queryset = Epiphan.objects.all()
    serializer_class = EpiphanSerializer
    permission_classes = (DjangoModelPermissions,)
    filter_fields = ()


class EpiphanChannelViewSet(ModelViewSet):
    queryset = EpiphanChannel.objects.all()
    serializer_class = EpiphanChannelSerializer
    permission_classes = (EpiphanChannelPermissions,)
    filter_fields = ("epiphan",)
    http_method_names = ModelViewSet.http_method_names + ["start", "stop"]

    @action(methods=["start", "stop"], detail=True)
    def control(self, request, pk):
        obj = get_object_or_404(EpiphanChannel, pk=pk)
        result = getattr(obj, request.method.lower())()
        return Response(result)


class EpiphanSourceViewSet(ModelViewSet):
    queryset = EpiphanSource.objects.all()
    serializer_class = EpiphanSourceSerializer
    permission_classes = (DjangoModelPermissions,)
    filter_fields = ("epiphan",)
