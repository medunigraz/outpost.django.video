# -*- coding: utf-8 -*-
# Generated by Django 1.11.27 on 2020-02-20 13:21
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('video', '0033_transcribelanguage'),
    ]

    operations = [
        migrations.AddField(
            model_name='recorder',
            name='auphonic',
            field=models.TextField(blank=True, null=True),
        ),
    ]
