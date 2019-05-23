# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-11-13 08:44
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("video", "0013_auto_20171031_2002")]

    operations = [
        migrations.AlterModelOptions(
            name="dashaudio",
            options={"permissions": (("view_dash_audio", "View DASH Audio"),)},
        ),
        migrations.AlterModelOptions(
            name="dashpublish", options={"permissions": (("view_dash", "View DASH"),)}
        ),
        migrations.AlterModelOptions(
            name="dashvideo",
            options={"permissions": (("view_dash_video", "View DASH Video"),)},
        ),
        migrations.AddField(
            model_name="epiphansource",
            name="audio",
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="epiphansource",
            name="port",
            field=models.PositiveIntegerField(default=554),
        ),
    ]
