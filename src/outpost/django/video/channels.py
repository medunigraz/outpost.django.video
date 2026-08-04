from django.urls import path

from . import consumers

urls = (path("video/player/<str:slug>/", consumers.PlayerConsumer.as_asgi()),)
