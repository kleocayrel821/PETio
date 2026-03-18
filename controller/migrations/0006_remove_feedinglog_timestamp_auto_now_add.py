# Generated manually to fix FeedingLog.timestamp field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('controller', '0005_device_scoping_and_events'),
    ]

    operations = [
        migrations.AlterField(
            model_name='feedinglog',
            name='timestamp',
            field=models.DateTimeField(),
        ),
    ]