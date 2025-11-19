from django.urls import path

from . import views

app_name = "video"

urlpatterns = [
    path(
        "live/room/<int:template_id>/<int:scene_id>/public/",
        views.LiveRoom.as_view(),
        {"public": True},
        name="live-room",
    ),
    path(
        "live/room/<int:template_id>/<int:scene_id>/",
        views.LiveRoom.as_view(),
        {"public": False},
        name="live-room",
    ),
    path(
        "live/room/<int:template_id>/",
        views.LiveRoom.as_view(),
        {"public": False, "scene_id": None},
        name="live-room",
    ),
    path(
        "live/event/<str:pk>/",
        views.LiveEvent.as_view(),
        name="live-event",
    ),
    path(
        "live/viewer/<str:event_id>/",
        views.LiveViewer.as_view(),
        name="live-viewer",
    ),
]
