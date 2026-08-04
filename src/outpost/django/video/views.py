import logging
import json
from ipaddress import ip_address
from parse import parse
from pathlib import Path

from braces.views import (
    CsrfExemptMixin,
    JsonRequestResponseMixin,
    JSONResponseMixin,
)
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.staticfiles import finders
from django.http import (
    HttpResponse,
    HttpResponseNotFound,
    HttpResponseServerError,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import (
    get_list_or_404,
    get_object_or_404,
)
from django.core.exceptions import SuspiciousOperation
from django.template import (
    Context,
    Template,
)
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext_lazy as _
from django.views.generic import (
    DetailView,
    View,
)
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.files.storage import FileSystemStorage
from rest_framework.authentication import TokenAuthentication
from formtools.wizard.views import NamedUrlSessionWizardView
from jsonschema import (
    ValidationError,
    validate,
)
from outpost.django.base.mixins import HttpBasicAuthMixin

from .conf import settings
from . import models, forms

logger = logging.getLogger(__name__)


class LiveRoom(
    CsrfExemptMixin, HttpBasicAuthMixin, LoginRequiredMixin, JSONResponseMixin, View
):
    def get(self, request, template_id, **kwargs):
        try:
            room = models.LiveTemplate.objects.get(pk=template_id)
        except models.LiveTemplate.DoesNotExist:
            return HttpResponseNotFound()
        if not room.channel.liveevent_set.filter(end__isnull=True).exists():
            return HttpResponseNotFound()
        return HttpResponse()

    @method_decorator(permission_required("video.add_liveevent", raise_exception=True))
    def post(self, request, template_id, scene_id, public):
        template = get_object_or_404(models.LiveTemplate, pk=template_id)
        scene = get_object_or_404(
            models.LiveTemplateScene, pk=scene_id, template=template
        )
        event = scene.instantiate(public)
        if not event.start():
            return HttpResponse(
                _(
                    "Maximum number of parallel transmissions reached - Live stream could not be started"
                ),
                status=503,
            )
        return HttpResponse()

    @method_decorator(
        permission_required("video.delete_liveevent", raise_exception=True)
    )
    def delete(self, request, template_id, **kwargs):
        template = get_object_or_404(models.LiveTemplate, pk=template_id)
        for event in get_list_or_404(
            template.channel.liveevent_set.all(), end__isnull=True
        ):
            event.stop()
        return HttpResponse()


class LiveEvent(JSONResponseMixin, DetailView):
    model = models.LiveEvent

    def get_queryset(self):
        return super().get_queryset().filter(end=None)

    def get(self, request, *args, **kwargs):
        return self.render_json_response({"viewer": self.get_object().viewer_count()})


class LiveViewer(
    CsrfExemptMixin,
    HttpBasicAuthMixin,
    LoginRequiredMixin,
    JsonRequestResponseMixin,
    View,
):
    @method_decorator(permission_required("video.add_liveviewer", raise_exception=True))
    def post(self, request, event_id):
        try:
            client = ip_address(self.request_json.get("client"))
        except Exception:
            client = None
        event = get_object_or_404(models.LiveEvent, pk=event_id)
        try:
            viewer = models.LiveViewer.objects.create(event=event, client=client)
        except models.LiveDeliveryServer.DoesNotExist:
            return HttpResponseServerError(
                _("Could not create a valid viewer instance")
            )

        logger.info(f"Created new viewer {viewer}")
        data = {
            "viewer": viewer.pk,
            "streams": {s.type: s.viewer(viewer) for s in event.livestream_set.all()},
        }
        return self.render_json_response(data)


class PushMixin(CsrfExemptMixin, JsonRequestResponseMixin):
    require_json = True

    def validate(self, data, schema):
        with open(finders.find(schema)) as f:
            try:
                validate(instance=data, schema=json.load(f))
            except ValidationError:
                logger.error(f"Invalid request {data}")
                return False
        return True


class PushAuthentication(PushMixin, View):
    def post(self, request, pk, **kwargs):
        if not self.validate(self.request_json, "video/schema/publish/auth.json"):
            return HttpResponseNotFound()

        logger.debug(self.request_json)
        action = self.request_json.get("action")
        logger.debug(f"Push authentication requested for action {action}")
        server = get_object_or_404(models.PushServer, pk=pk)
        if action == "api":
            if not server.username and not server.password:
                logger.debug(f"Server {server} has no credentials set")
                return HttpResponse(status=200)
            username = self.request_json.get("user")
            password = self.request_json.get("password")
            if server.username != username or server.password != password:
                logger.debug(f"Server {server} does not accept provided credentials")
                return HttpResponseNotFound()
            return HttpResponse(status=200)
        if action == "read":
            protocol = self.request_json.get("protocol")
            if protocol != settings.VIDEO_PUSH_READER_PROTOCOL:
                logger.error(f"Reader does not support protocol {protocol}")
                return HttpResponseNotFound()
        if action == "publish":
            protocol = get_object_or_404(
                models.PushProtocol, identifier=self.request_json.get("protocol")
            )
            path = self.request_json.get("path")
            ingest = get_object_or_404(
                models.PushLiveIngest, pk=protocol.parse_path(path)
            )
            if protocol != ingest.ingest.protocol:
                logger.error(
                    f"Push ingest {ingest} does not support protocol {protocol}"
                )
                return HttpResponseNotFound()
        return HttpResponse(status=200)


class PushReady(PushMixin, View):
    require_json = True

    def post(self, request, pk, **kwargs):
        if not self.validate(self.request_json, "video/schema/publish/ready.json"):
            return HttpResponseNotFound()
        logger.debug(self.request_json)
        identifier = parse("{name}Conn", self.request_json.get("type")).named.get(
            "name"
        )
        protocol = get_object_or_404(models.PushProtocol, identifier=identifier)
        path = self.request_json.get("path")
        logger.debug(f"Signaling ingest stream ready for {path}")
        ingest = get_object_or_404(
            models.PushLiveIngest, pk=protocol.parse_path(path), ingest__server__pk=pk
        )
        logger.debug(f"Ingest {ingest} ready")
        ingest.ready()
        return HttpResponse(status=200)


class PushNotReady(PushMixin, View):
    require_json = True

    def post(self, request, pk, **kwargs):
        if not self.validate(self.request_json, "video/schema/publish/ready.json"):
            return HttpResponseNotFound()
        identifier = parse("{name}Conn", self.request_json.get("type")).named.get(
            "name"
        )
        protocol = get_object_or_404(models.PushProtocol, identifier=identifier)
        path = self.request_json.get("path")
        logger.debug(f"Signaling ingest stream not ready for {path}")
        ingest = get_object_or_404(
            models.PushLiveIngest, pk=protocol.parse_path(path), ingest__server__pk=pk
        )
        logger.debug(f"Ingest {ingest} not ready")
        ingest.not_ready()
        return HttpResponse(status=200)


class PushViewer(APIView):
    authentication_classes = [TokenAuthentication]

    def post(self, request, pk, format=None):
        event = get_object_or_404(models.PushLiveEvent, pk=pk)
        if not event.public:
            if request.user not in event.users:
                return HttpResponseForbidden()
        client = request.META.get("REMOTE_ADDR")
        try:
            viewer = models.LiveViewer.objects.create(event=event, client=client)
        except models.LiveDeliveryServer.DoesNotExist:
            return HttpResponseServerError(
                _("Could not create a valid viewer instance")
            )
        logger.info(f"Created new viewer {viewer}")
        data = {
            "viewer": viewer.pk,
            "streams": {s.type: s.viewer(viewer) for s in event.livestream_set.all()},
            "room": event.room,
            "title": event.title,
            "stylesheet": event.stylesheet,
            "logo": event.logo,
            "intro": event.intro,
        }
        return Response(data)


class PushEventWizard(NamedUrlSessionWizardView):
    form_list = (
        ("event", forms.PushLiveEventForm),
        ("ingest", forms.PushLiveIngestForm),
        ("users", forms.PushEventUserForm),
    )
    initial_dict = {
        "event": {
            "list_size": 20,
            "delete_threshold": 100,
        },
    }
    done_step_name = "finished"
    file_storage = FileSystemStorage(location=str(Path(settings.MEDIA_ROOT).joinpath('push-event-wizard')))

    def get_template_names(self):
        return (f"video/push/create/{self.steps.current}.html", "video/push/create/default.html")

    def done(self, form_list, **kwargs):
        print(form_list)
        return HttpResponseRedirect("/page-to-redirect-to-when-done/")


# class PushRead(PushMixin, View):
#    require_json = True
#
#    def post(self, request, **kwargs):
#        if not self.validate(self.request_json, "video/schema/publish/read.json")):
#            return HttpResponseNotFound()
#        path = self.request_json.get("path")
#        stream = get_object_or_404(models.PushStream, pk=self.parse_path(path))
#        stream.read()
#
#
# class PushUnRead(PushMixin, View):
#    require_json = True
#
#    def post(self, request, **kwargs):
#        if not self.validate(self.request_json, "video/schema/publish/read.json")):
#            return HttpResponseNotFound()
#        path = self.request_json.get("path")
#        stream = get_object_or_404(models.PushStream, pk=self.parse_path(path))
#        stream.un_read()
