# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2020-08-05 12:03
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('video', '0034_recorder_auphonic'),
    ]

    operations = [
        migrations.AlterField(
            model_name='epiphanrecording',
            name='channel',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='video.EpiphanChannel'),
        ),
        migrations.AlterField(
            model_name='epiphansource',
            name='input',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='video.Input'),
        ),
    ]
