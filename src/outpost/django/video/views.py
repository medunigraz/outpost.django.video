import logging

from django.shortcuts import get_object_or_404, get_list_or_404
from django.views.generic import View
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.template import Context, Template

from braces.views import JSONResponseMixin

from . import models

logger = logging.getLogger(__name__)

class LiveRoom(LoginRequiredMixin, View):

    def get(self, template_id):
        room = get_object_or_404(models.LiveTemplate, pk=template_id)
        get_list_or_404(room.channel.liveevent_set, end__is_null=True)
        return HttpResponse()

    @method_decorator(permission_required('video.add_liveevent', raise_exception=True))
    def post(self, template_id, scene_id, public):
        template = get_object_or_404(models.LiveTemplate, pk=template_id)
        scene = get_object_or_404(models.LiveTemplateScene, pk=scene_id, template=template)
        event = scene.instantiate(public)
        event.run()
        return HttpResponse()

    @method_decorator(permission_required('video.delete_liveevent', raise_exception=True))
    def delete(self, template_id):
        template = get_object_or_404(models.LiveTemplate, pk=template_id)
        for le in get_list_or_404(template.channel.liveevent_set.all(), end__is_null=True):
            le.stop()
        return HttpResponse()


class LiveViewer(LoginRequiredMixin, JSONResponseMixin, View):

    @method_decorator(permission_required('video.add_liveviewer', raise_exception=True))
    def post(self, event_id):
        event = get_object_or_404(models.LiveEvent, pk=event_id)
        viewer = models.LiveViewer.objects.create(
            event=event
        )
        logger.info(f"Created new viewer {viewer}")
        data = {
            "viewer": viewer.pk,
            "streams": {s.type: s.viewer(viewer) for s in event.streams},

        }
        return self.render_json_response(data)

