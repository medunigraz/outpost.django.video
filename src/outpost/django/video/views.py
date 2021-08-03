import logging

from braces.views import CsrfExemptMixin, JSONResponseMixin
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_list_or_404, get_object_or_404
from django.template import Context, Template
from django.utils.decorators import method_decorator
from django.views.generic import View
from outpost.django.base.mixins import HttpBasicAuthMixin

from . import models

logger = logging.getLogger(__name__)


class LiveRoom(CsrfExemptMixin, HttpBasicAuthMixin, LoginRequiredMixin, View):
    def get(self, request, template_id, **kwargs):
        room = get_object_or_404(models.LiveTemplate, pk=template_id)
        get_list_or_404(room.channel.liveevent_set, end__isnull=True)
        return HttpResponse()

    @method_decorator(permission_required("video.add_liveevent", raise_exception=True))
    def post(self, request, template_id, scene_id, public):
        template = get_object_or_404(models.LiveTemplate, pk=template_id)
        scene = get_object_or_404(
            models.LiveTemplateScene, pk=scene_id, template=template
        )
        event = scene.instantiate(public)
        event.start()
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
    CsrfExemptMixin, HttpBasicAuthMixin, LoginRequiredMixin, JSONResponseMixin, View
):
    @method_decorator(permission_required("video.add_liveviewer", raise_exception=True))
    def post(self, request, event_id):
        event = get_object_or_404(models.LiveEvent, pk=event_id)
        viewer = models.LiveViewer.objects.create(event=event)
        logger.info(f"Created new viewer {viewer}")
        data = {
            "viewer": viewer.pk,
            "streams": {s.type: s.viewer(viewer) for s in event.streams},
        }
        return self.render_json_response(data)
