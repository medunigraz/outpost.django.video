# Generated by Django 2.2.28 on 2023-11-06 19:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("video", "0046_liveviewer_client"),
    ]

    operations = [
        migrations.AddField(
            model_name="livedeliveryserver",
            name="enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="epiphansource",
            name="url",
            field=models.URLField(null=True),
        ),
    ]
