# Generated by Django 2.2.24 on 2022-01-25 08:51

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("video", "0040_auto_20220124_1424"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveviewer",
            name="statistics",
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True),
        ),
        migrations.DeleteModel(
            name="LiveViewerStatistic",
        ),
    ]
