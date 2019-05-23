# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-03-12 13:05
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('campusonline', '0012_event'),
        ('video', '0023_auto_20180309_1342'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='recording',
            name='course_group_term',
        ),
        migrations.AddField(
            model_name='recording',
            name='course',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='campusonline.Course'),
        ),
        migrations.AddField(
            model_name='recording',
            name='presenter',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='campusonline.Person'),
        ),
    ]
