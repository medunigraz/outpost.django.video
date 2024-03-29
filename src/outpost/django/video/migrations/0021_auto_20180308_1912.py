# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-03-08 18:12
from __future__ import unicode_literals

from django.db import (
    migrations,
    models,
)


class Migration(migrations.Migration):

    dependencies = [("video", "0020_auto_20180207_1528")]

    operations = [
        migrations.AlterModelOptions(name="eventaudio", options={}),
        migrations.AlterModelOptions(name="eventmedia", options={}),
        migrations.AlterModelOptions(name="eventvideo", options={}),
        migrations.AlterModelOptions(name="export", options={}),
        migrations.AlterModelOptions(name="input", options={}),
        migrations.AlterModelOptions(name="publish", options={}),
        migrations.AlterModelOptions(name="publishmedia", options={}),
        migrations.AlterModelManagers(name="export", managers=[]),
        migrations.AlterModelManagers(name="sidebysideexport", managers=[]),
        migrations.AlterModelManagers(name="zipstreamexport", managers=[]),
        migrations.AddField(
            model_name="recording",
            name="archived",
            field=models.BooleanField(default=False),
        ),
    ]
