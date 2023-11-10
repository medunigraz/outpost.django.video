import logging
from ipaddress import ip_address

from braces.views import (
    CsrfExemptMixin,
    JsonRequestResponseMixin,
    JSONResponseMixin,
)
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import (
    HttpResponse,
    HttpResponseNotFound,
    HttpResponseServerError,
)
from django.shortcuts import (
    get_list_or_404,
    get_object_or_404,
)
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
from outpost.django.base.mixins import HttpBasicAuthMixin

from . import models

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
