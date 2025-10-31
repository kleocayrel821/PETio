from django.db import migrations, models
from django.conf import settings


def map_processed_to_completed(apps, schema_editor):
    PendingCommand = apps.get_model('controller', 'PendingCommand')
    PendingCommand.objects.filter(status='processed').update(status='completed')


def backfill_device_ids(apps, schema_editor):
    PendingCommand = apps.get_model('controller', 'PendingCommand')
    FeedingLog = apps.get_model('controller', 'FeedingLog')
    default_device = getattr(settings, 'DEVICE_ID', 'feeder-1')
    PendingCommand.objects.filter(device_id__isnull=True).update(device_id=default_device)
    FeedingLog.objects.filter(device_id__isnull=True).update(device_id=default_device)


class Migration(migrations.Migration):

    dependencies = [
        ('controller', '0004_devicestatus'),
    ]

    operations = [
        # Add device_id to PendingCommand
        migrations.AddField(
            model_name='pendingcommand',
            name='device_id',
            field=models.CharField(max_length=64, db_index=True, default='feeder-1'),
        ),
        # Add device_id to FeedingLog
        migrations.AddField(
            model_name='feedinglog',
            name='device_id',
            field=models.CharField(max_length=64, db_index=True, default='feeder-1'),
        ),
        # Create CommandEvent model
        migrations.CreateModel(
            name='CommandEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_status', models.CharField(max_length=20, blank=True, default='')),
                ('to_status', models.CharField(max_length=20)),
                ('device_id', models.CharField(max_length=64, db_index=True, default='feeder-1')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('command', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='events', to='controller.pendingcommand')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='commandevent',
            index=models.Index(fields=['command', 'to_status', 'created_at'], name='commandevent_cmd_status_created_idx'),
        ),
        # Add composite index to PendingCommand for status + created_at
        migrations.AddIndex(
            model_name='pendingcommand',
            index=models.Index(fields=['status', 'created_at'], name='pendingcommand_status_created_idx'),
        ),
        # Data migration: processed -> completed
        migrations.RunPython(map_processed_to_completed, reverse_code=migrations.RunPython.noop),
        # Backfill device_id values where null
        migrations.RunPython(backfill_device_ids, reverse_code=migrations.RunPython.noop),
    ]