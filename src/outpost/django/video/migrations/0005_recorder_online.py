# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2017-08-22 18:17
from __future__ import unicode_literals

from django.db import (
    migrations,
    models,
)


class Migration(migrations.Migration):

    dependencies = [("video", "0004_auto_20170820_2011")]

    operations = [
        migrations.AddField(
            model_name="recorder",
            name="online",
            field=models.BooleanField(default=False),
        )
    ]
