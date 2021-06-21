# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2021-06-17 12:53
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import django_extensions.db.fields
import markupfield.fields
import outpost.django.base.validators


class Migration(migrations.Migration):

    dependencies = [
        ('geo', '0021_auto_20200805_1403'),
        ('django_sshworker', '0002_auto_20210519_1504'),
        ('video', '0035_auto_20200805_1403'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiveChannel',
            fields=[
                ('id', django_extensions.db.fields.ShortUUIDField(blank=True, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=512)),
                ('enabled', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='LiveDeliveryServer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('base', models.URLField()),
                ('config', models.CharField(max_length=256, validators=[outpost.django.base.validators.RedisURLValidator()])),
                ('online', models.BooleanField(default=False, editable=False)),
                ('timeout', models.PositiveSmallIntegerField(default=5)),
            ],
        ),
        migrations.CreateModel(
            name='LiveEvent',
            fields=[
                ('id', django_extensions.db.fields.ShortUUIDField(blank=True, editable=False, primary_key=True, serialize=False)),
                ('public', models.BooleanField(default=False)),
                ('begin', models.DateTimeField(editable=False, null=True)),
                ('end', models.DateTimeField(editable=False, null=True)),
                ('title', models.CharField(max_length=512)),
                ('description', markupfield.fields.MarkupField(rendered_field=True)),
                ('description_markup_type', models.CharField(choices=[('', '--'), ('markdown', 'markdown'), ('ReST', 'ReST')], default='markdown', max_length=30)),
                ('_description_rendered', models.TextField(editable=False)),
                ('channel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveChannel')),
                ('delivery', models.ManyToManyField(to='video.LiveDeliveryServer')),
                ('job', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, to='django_sshworker.Job')),
            ],
        ),
        migrations.CreateModel(
            name='LivePortal',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=512)),
                ('control', models.URLField()),
            ],
        ),
        migrations.CreateModel(
            name='LiveStream',
            fields=[
                ('id', django_extensions.db.fields.ShortUUIDField(blank=True, editable=False, primary_key=True, serialize=False)),
                ('type', models.CharField(max_length=128)),
                ('source', models.CharField(max_length=512)),
                ('list_size', models.PositiveIntegerField()),
                ('delete_threshold', models.PositiveIntegerField()),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveEvent')),
            ],
        ),
        migrations.CreateModel(
            name='LiveStreamStatistic',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datetime', models.DateTimeField()),
                ('viewers', models.PositiveIntegerField(default=0)),
                ('stream', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveStream')),
            ],
        ),
        migrations.CreateModel(
            name='LiveStreamVariant',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('height', models.PositiveSmallIntegerField()),
                ('preset', models.CharField(max_length=32)),
                ('profile', models.CharField(max_length=32)),
                ('video', models.CharField(max_length=16)),
                ('audio', models.CharField(max_length=16)),
            ],
        ),
        migrations.CreateModel(
            name='LiveStreamVariantRequirement',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slots', models.PositiveIntegerField()),
                ('resource', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='django_sshworker.Resource')),
                ('variant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveStreamVariant')),
            ],
        ),
        migrations.CreateModel(
            name='LiveTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('title', models.CharField(max_length=512)),
                ('description', markupfield.fields.MarkupField(rendered_field=True)),
                ('description_markup_type', models.CharField(choices=[('', '--'), ('markdown', 'markdown'), ('ReST', 'ReST')], default='markdown', max_length=30)),
                ('_description_rendered', models.TextField(editable=False)),
                ('channel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveChannel')),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='geo.Room')),
            ],
        ),
        migrations.CreateModel(
            name='LiveTemplateScene',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveTemplate')),
            ],
        ),
        migrations.CreateModel(
            name='LiveTemplateStream',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(max_length=128)),
                ('list_size', models.PositiveIntegerField()),
                ('delete_threshold', models.PositiveIntegerField()),
                ('scene', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveTemplateScene')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.EpiphanSource')),
                ('variants', models.ManyToManyField(to='video.LiveStreamVariant')),
            ],
        ),
        migrations.CreateModel(
            name='LiveViewer',
            fields=[
                ('id', django_extensions.db.fields.ShortUUIDField(blank=True, editable=False, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('delivery', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveDeliveryServer')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveEvent')),
            ],
        ),
        migrations.CreateModel(
            name='LiveViewerStatistic',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datetime', models.DateTimeField()),
                ('stream', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveStream')),
                ('viewer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video.LiveViewer')),
            ],
        ),
        migrations.AddField(
            model_name='livestream',
            name='variants',
            field=models.ManyToManyField(to='video.LiveStreamVariant'),
        ),
        migrations.AddField(
            model_name='livechannel',
            name='portals',
            field=models.ManyToManyField(to='video.LivePortal'),
        ),
    ]
