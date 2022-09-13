# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-11-22 14:21
from __future__ import unicode_literals

import django.utils.timezone
import django_extensions.db.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("video", "0015_auto_20171117_1417")]

    operations = [
        migrations.AlterModelOptions(
            name="export",
            options={
                "get_latest_by": "modified",
                "ordering": ("-modified", "-created"),
            },
        ),
        migrations.AddField(
            model_name="export",
            name="created",
            field=django_extensions.db.fields.CreationDateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name="created",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="export",
            name="modified",
            field=django_extensions.db.fields.ModificationDateTimeField(
                auto_now=True, verbose_name="modified"
            ),
        ),
    ]
