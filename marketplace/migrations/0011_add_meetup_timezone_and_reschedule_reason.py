from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0010_alter_transactionlog_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="meetup_timezone",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="transaction",
            name="reschedule_reason",
            field=models.TextField(blank=True, default=""),
        ),
    ]