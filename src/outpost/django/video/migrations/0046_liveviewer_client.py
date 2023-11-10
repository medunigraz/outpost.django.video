# Generated by Django 2.2.28 on 2023-06-06 11:41

from django.db import migrations
import netfields.fields


class Migration(migrations.Migration):

    dependencies = [
        ("video", "0045_livedeliveryservercountry_livedeliveryservernetwork"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveviewer",
            name="client",
            field=netfields.fields.InetAddressField(
                blank=True, max_length=39, null=True
            ),
        ),
    ]