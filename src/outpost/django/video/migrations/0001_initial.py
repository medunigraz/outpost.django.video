# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2017-08-18 13:23
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import django_extensions.db.fields
from ...base.utils import Uuid4Upload


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("geo", "0015_auto_20170809_0948"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="Recorder",
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
                ("hostname", models.CharField(max_length=128)),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="Server",
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
                ("hostname", models.CharField(blank=True, max_length=128)),
                ("port", models.PositiveIntegerField(default=2022)),
                ("key", models.BinaryField(default=b"")),
                ("active", models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="Epiphan",
            fields=[
                (
                    "recorder_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="video.Recorder",
                    ),
                ),
                ("username", models.CharField(max_length=128)),
                ("password", models.CharField(max_length=128)),
                ("key", models.BinaryField(null=True)),
                ("active", models.BooleanField(default=True)),
            ],
            options={"abstract": False},
            bases=("video.recorder",),
        ),
        migrations.AlterUniqueTogether(
            name="server", unique_together=set([("hostname", "port")])
        ),
        migrations.AddField(
            model_name="recorder",
            name="polymorphic_ctype",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="polymorphic_video.recorder_set+",
                to="contenttypes.ContentType",
            ),
        ),
        migrations.AddField(
            model_name="epiphan",
            name="server",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="video.Server",
            ),
        ),
        migrations.CreateModel(
            name="Recording",
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
                (
                    "created",
                    django_extensions.db.fields.CreationDateTimeField(
                        auto_now_add=True, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    django_extensions.db.fields.ModificationDateTimeField(
                        auto_now=True, verbose_name="modified"
                    ),
                ),
                ("data", models.FileField(upload_to=Uuid4Upload)),
                (
                    "recorder",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="video.Recorder"
                    ),
                ),
                ("info", django.contrib.postgres.fields.jsonb.JSONField(default={})),
            ],
            options={
                "abstract": False,
                "ordering": ("-modified", "-created"),
                "get_latest_by": "modified",
            },
        ),
        migrations.CreateModel(
            name="Export",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                )
            ],
            options={"abstract": False},
        ),
        migrations.RemoveField(model_name="epiphan", name="active"),
        migrations.AddField(
            model_name="recorder",
            name="active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="recorder",
            name="room",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="geo.Room",
            ),
        ),
        migrations.AlterField(
            model_name="epiphan",
            name="key",
            field=models.BinaryField(default=b""),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name="SideBySideExport",
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
            options={"abstract": False},
            bases=("video.export",),
        ),
        migrations.AddField(
            model_name="export",
            name="polymorphic_ctype",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="polymorphic_video.export_set+",
                to="contenttypes.ContentType",
            ),
        ),
        migrations.AddField(
            model_name="export",
            name="recording",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="video.Recording"
            ),
        ),
    ]
