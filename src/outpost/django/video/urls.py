from django.conf.urls import url

from . import views

app_name = "video"

urlpatterns = [
    url(
        r"^live/room/(?P<template_id>[0-9]+)/(?P<scene_id>[0-9]+)/public/$",
        views.LiveRoom.as_view(),
        {"public": True},
        name="live-room",
    ),
    url(
        r"^live/room/(?P<template_id>[0-9]+)/(?P<scene_id>[0-9]+)/$",
        views.LiveRoom.as_view(),
        {"public": False},
        name="live-room",
    ),
    url(
        r"^live/room/(?P<template_id>[0-9]+)/$",
        views.LiveRoom.as_view(),
        {"public": False, "scene_id": None},
        name="live-room",
    ),
    url(
        r"^live/event/(?P<pk>[\w]+)/$",
        views.LiveEvent.as_view(),
        name="live-event",
    ),
    url(
        r"^live/viewer/(?P<event_id>[\w]+)/$",
        views.LiveViewer.as_view(),
        name="live-viewer",
    ),
    url(
        r"^push/auth/(?P<pk>\d+)$",
        views.PushAuthentication.as_view(),
        name="push-auth",
    ),
    url(
        r"^push/ready/(?P<pk>\d+)$",
        views.PushReady.as_view(),
        name="push-ready",
    ),
    url(
        r"^push/notready/(?P<pk>\d+)$",
        views.PushNotReady.as_view(),
        name="push-not-ready",
    ),
    url(
        r"^push/viewer/(?P<pk>\d+)$",
        views.PushViewer.as_view(),
        name="push-viewer",
    ),
    url(
        r"^push/create/(?:(?P<step>.+)/)?$",
        views.PushEventWizard.as_view(url_name=f"{app_name}:push-create"),
        name="push-create",
    ),
]
