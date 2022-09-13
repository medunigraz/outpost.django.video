# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-06-15 11:35
from __future__ import unicode_literals

import datetime
import re

import django.core.files.storage
import django.core.validators
import django.db.models.deletion
from django.db import (
    migrations,
    models,
)

from ...base.utils import Uuid4Upload


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("video", "0026_recording_ready"),
    ]

    operations = [
        migrations.AlterModelOptions(name="epiphanrecording", options={}),
        migrations.RemoveField(model_name="recording", name="archived"),
        migrations.RemoveField(model_name="recording", name="data"),
        migrations.AddField(
            model_name="epiphan",
            name="ntp",
            field=models.CharField(
                default="0.pool.ntp.org 1.pool.ntp.org 2.pool.ntp.org 3.pool.ntp.org",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="epiphan",
            name="version",
            field=models.CharField(default="0", max_length=16),
        ),
        migrations.AddField(
            model_name="epiphanchannel",
            name="sizelimit",
            field=models.CharField(
                default="1GiB",
                max_length=16,
                validators=[
                    django.core.validators.RegexValidator(
                        code="no_filesize",
                        message="Size limit must be an integer followed by a SI unit",
                        regex=re.compile("^\\d+(?:[kmgtpe]i?b?)?$", 34),
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="epiphanchannel",
            name="timelimit",
            field=models.DurationField(default=datetime.timedelta(0, 10800)),
        ),
        migrations.AddField(
            model_name="recording",
            name="archive",
            field=models.FileField(
                default=None,
                null=True,
                storage=django.core.files.storage.FileSystemStorage(
                    location="/archive"
                ),
                upload_to=Uuid4Upload,
            ),
        ),
        migrations.AddField(
            model_name="recording",
            name="online",
            field=models.FileField(null=True, upload_to=Uuid4Upload),
        ),
        migrations.AddField(
            model_name="recording",
            name="polymorphic_ctype",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="polymorphic_video.recording_set+",
                to="contenttypes.ContentType",
            ),
        ),
    ]
