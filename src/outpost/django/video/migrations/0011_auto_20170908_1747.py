# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-09-08 15:47
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("video", "0010_auto_20170908_1007")]

    operations = [
        migrations.AlterModelOptions(
            name="epiphanchannel", options={"ordering": ("name",)}
        ),
        migrations.AlterModelOptions(
            name="epiphansource", options={"ordering": ("number",)}
        ),
        migrations.AlterModelOptions(
            name="recorder", options={"ordering": ("name", "hostname")}
        ),
        migrations.AlterModelOptions(
            name="recording", options={"ordering": ("created",)}
        ),
        migrations.AlterModelOptions(
            name="server", options={"ordering": ("hostname", "port")}
        ),
    ]
