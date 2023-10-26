from django.http import Http404
from django.shortcuts import get_object_or_404
from guardian.shortcuts import get_objects_for_user
from outpost.django.api.permissions import (
    ExtendedDjangoModelPermissions,
    ExtendedDjangoObjectPermissions,
)
from outpost.django.base.decorators import docstring_format
from rest_flex_fields.views import FlexFieldsMixin
from rest_framework.decorators import action
from rest_framework.generics import (
    ListAPIView,
    RetrieveAPIView,
)
from rest_framework.permissions import (
    DjangoModelPermissions,
    DjangoModelPermissionsOrAnonReadOnly,
    IsAuthenticated,
)
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import (
    GenericViewSet,
    ModelViewSet,
    ReadOnlyModelViewSet,
)

from .conf import settings
from .models import (  # Broadcast,; EventAudio,; EventMedia,; EventVideo,; Publish,; Stream,; Token,
    Epiphan,
    EpiphanChannel,
    EpiphanInput,
    EpiphanMedia,
    EpiphanSource,
    Export,
    LiveChannel,
    LiveTemplate,
    LiveTemplateScene,
    Recorder,
    Recording,
    RecordingAsset,
)
from .permissions import EpiphanChannelPermissions
from .serializers import (
    EpiphanChannelSerializer,
    EpiphanInputSerializer,
    EpiphanMediaSerializer,
    EpiphanSerializer,
    EpiphanSourceSerializer,
    ExportClassSerializer,
    LiveChannelSerializer,
    LiveTemplateSceneSerializer,
    LiveTemplateSerializer,
    RecorderSerializer,
    RecordingAssetSerializer,
    RecordingSerializer,
)
from .tasks import ExportTasks


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
        task = ExportTasks.create.apply_async(
            (recording, exporter, request.build_absolute_uri("/")),
            queue=settings.VIDEO_CELERY_QUEUE,
        )
        result = {"task": task.id}
        return Response(result)


class RecorderViewSet(ModelViewSet):
    queryset = Recorder.objects.all()
    serializer_class = RecorderSerializer
    permission_classes = (ExtendedDjangoModelPermissions,)
    filter_fields = ()

    def get_queryset(self):
        qs = super().get_queryset()
        view = f"{qs.model._meta.app_label}.view_recorder"
        change = f"{qs.model._meta.app_label}.change_recorder"
        return get_objects_for_user(
            self.request.user,
            (view, change),
            klass=self.queryset,
            accept_global_perms=True,
            any_perm=True,
        )


class RecordingViewSet(ModelViewSet):
    queryset = Recording.objects.all()
    serializer_class = RecordingSerializer
    permission_classes = (DjangoModelPermissions,)
    filter_fields = ("recorder",)

    def get_queryset(self):
        qs = super().get_queryset()
        view = f"{qs.model._meta.app_label}.view_recorder"
        change = f"{qs.model._meta.app_label}.change_recorder"
        recorders = get_objects_for_user(
            self.request.user,
            (view, change),
            Recorder.objects.all(),
            accept_global_perms=True,
            any_perm=True,
        )
        return qs.filter(ready=True, recorder__in=recorders)


class RecordingAssetViewSet(ModelViewSet):
    queryset = RecordingAsset.objects.all()
    serializer_class = RecordingAssetSerializer
    permission_classes = (DjangoModelPermissions,)
    filter_fields = ("recording", "mimetype")

    def get_queryset(self):
        qs = super().get_queryset()
        view = f"{qs.model._meta.app_label}.view_recorder"
        change = f"{qs.model._meta.app_label}.change_recorder"
        recorders = get_objects_for_user(
            self.request.user,
            (view, change),
            Recorder.objects.all(),
            accept_global_perms=True,
            any_perm=True,
        )
        return qs.filter(recording__recorder__in=recorders)


class EpiphanViewSet(ModelViewSet):
    queryset = Recorder.objects.instance_of(Epiphan).filter(enabled=True)
    serializer_class = EpiphanSerializer
    permission_classes = (ExtendedDjangoObjectPermissions,)
    filter_fields = ()

    def get_queryset(self):
        qs = super().get_queryset()
        view = f"{qs.model._meta.app_label}.view_recorder"
        change = f"{qs.model._meta.app_label}.change_recorder"
        return get_objects_for_user(
            self.request.user,
            (view, change),
            qs.non_polymorphic(),
            accept_global_perms=True,
            any_perm=True,
        )


class EpiphanChannelViewSet(ModelViewSet):
    queryset = EpiphanChannel.objects.filter(epiphan__enabled=True)
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
    queryset = EpiphanSource.objects.filter(epiphan__enabled=True)
    serializer_class = EpiphanSourceSerializer
    permission_classes = (ExtendedDjangoModelPermissions,)
    filter_fields = ("epiphan",)


class EpiphanMediaViewSet(ModelViewSet):
    queryset = EpiphanMedia.objects.filter(epiphan__enabled=True)
    serializer_class = EpiphanMediaSerializer
    permission_classes = (ExtendedDjangoModelPermissions,)
    filter_fields = ("epiphan",)


class EpiphanInputViewSet(ModelViewSet):
    queryset = EpiphanInput.objects.filter(epiphan__enabled=True)
    serializer_class = EpiphanInputSerializer
    permission_classes = (ExtendedDjangoModelPermissions,)
    filter_fields = ("epiphan",)


@docstring_format(model=LiveChannel.__doc__, serializer=LiveChannelSerializer.__doc__)
class LiveChannelViewSet(ReadOnlyModelViewSet):
    queryset = LiveChannel.objects.filter(enabled=True)
    serializer_class = LiveChannelSerializer
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly,)
    # filter_fields = ("epiphan",)


@docstring_format(model=LiveTemplate.__doc__, serializer=LiveTemplateSerializer.__doc__)
class LiveTemplateViewSet(FlexFieldsMixin, ReadOnlyModelViewSet):
    queryset = LiveTemplate.objects.all()
    serializer_class = LiveTemplateSerializer
    permission_classes = (ExtendedDjangoModelPermissions,)
    permit_list_expands = ("livetemplatescene_set",)
    # filter_fields = ("epiphan",)


@docstring_format(
    model=LiveTemplateScene.__doc__, serializer=LiveTemplateSceneSerializer.__doc__
)
class LiveTemplateSceneViewSet(ReadOnlyModelViewSet):
    queryset = LiveTemplateScene.objects.all()
    serializer_class = LiveTemplateSceneSerializer
    permission_classes = (ExtendedDjangoModelPermissions,)
    # filter_fields = ("epiphan",)
