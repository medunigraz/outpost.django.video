# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2017-09-06 09:11
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import (
    migrations,
    models,
)

from ...base.utils import Uuid4Upload


class Migration(migrations.Migration):

    dependencies = [("video", "0007_auto_20170828_1958")]

    operations = [
        migrations.CreateModel(
            name="ZipStreamExport",
            fields=[
                (
                    "export_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="video.Export",
                    ),
                ),
                ("data", models.FileField(upload_to=Uuid4Upload)),
            ],
            options={"verbose_name": "Zip-Stream"},
            bases=("video.export",),
        )
    ]
