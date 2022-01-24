# Generated by Django 2.2.24 on 2022-01-24 13:24

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('video', '0039_liveevent_started'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='epiphanrecording',
            options={'get_latest_by': 'modified'},
        ),
        migrations.AlterModelOptions(
            name='export',
            options={'get_latest_by': 'modified'},
        ),
        migrations.AlterModelOptions(
            name='input',
            options={'base_manager_name': 'objects'},
        ),
        migrations.AlterModelOptions(
            name='recorder',
            options={'ordering': ('name', 'hostname'), 'permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='recording',
            options={'ordering': ('-created',), 'permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='recordingasset',
            options={'ordering': ('-created',), 'permissions': ()},
        ),
        migrations.AddField(
            model_name='liveviewerstatistic',
            name='variant',
            field=models.ForeignKey(default=0, on_delete=django.db.models.deletion.CASCADE, to='video.LiveStreamVariant'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='transcribelanguage',
            name='order',
            field=models.PositiveIntegerField(db_index=True, editable=False, verbose_name='order'),
        ),
    ]
