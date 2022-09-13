# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-11-17 13:17
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import (
    migrations,
    models,
)


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("video", "0014_auto_20171113_0944"),
    ]

    operations = [
        migrations.CreateModel(
            name="Input",
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
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="PanasonicCamera",
            fields=[
                (
                    "input_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="video.Input",
                    ),
                ),
                ("hostname", models.CharField(max_length=128)),
                ("enabled", models.BooleanField(default=True)),
                ("online", models.BooleanField(default=False)),
            ],
            options={"abstract": False},
            bases=("video.input", models.Model),
        ),
        migrations.AddField(
            model_name="input",
            name="polymorphic_ctype",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="polymorphic_video.input_set+",
                to="contenttypes.ContentType",
            ),
        ),
        migrations.AddField(
            model_name="epiphansource",
            name="input",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="video.Input",
            ),
        ),
    ]
