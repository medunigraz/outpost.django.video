# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2017-08-19 22:14
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [("video", "0002_auto_20170818_1538")]

    operations = [
        migrations.CreateModel(
            name="EpiphanChannel",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=128)),
                ("path", models.CharField(max_length=10)),
                (
                    "epiphan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="video.Epiphan"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="EpiphanRecording",
            fields=[
                (
                    "recording_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="video.Recording",
                    ),
                ),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="video.EpiphanChannel",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "get_latest_by": "modified",
                "ordering": ("-modified", "-created"),
            },
            bases=("video.recording",),
        ),
        migrations.AlterField(
            model_name="recording",
            name="info",
            field=django.contrib.postgres.fields.jsonb.JSONField(null=True),
        ),
    ]
