from django.conf.urls import url

from . import views

app_name = "video"

urlpatterns = [
    url(r'^live/room/(?P<template_id>[0-9]+)/(?P<scene_id>[0-9]+)/public/$', views.LiveRoom.as_view(), {'public': True}, name='live-room'),
    url(r'^live/room/(?P<template_id>[0-9]+)/(?P<scene_id>[0-9]+)/$', views.LiveRoom.as_view(), {'public': False}, name='live-room'),
    url(r'^live/room/(?P<template_id>[0-9]+)/$', views.LiveRoom.as_view(), {'public': False, scene_id=None}, name='live-room'),
    url(r'^live/viewer/(?P<event_id>[0-9]+)/$', views.LiveViewer.as_view(), name='live-viewer'),
]
