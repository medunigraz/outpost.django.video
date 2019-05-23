# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-06-27 17:44
from __future__ import unicode_literals

from django.db import migrations


def forwards_func(apps, schema_editor):
    Recording = apps.get_model('video', 'Recording')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    new_ct = ContentType.objects.get_for_model(Recording)
    Recording.objects.filter(polymorphic_ctype__isnull=True).update(polymorphic_ctype=new_ct)


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0001_initial'),
        ('video', '0028_epiphansource_name'),
    ]

    operations = [
        migrations.RunPython(forwards_func, migrations.RunPython.noop),
    ]
