from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0020_notification_related_thread_transaction_thread"),
    ]

    operations = [
        migrations.AddField(
            model_name="listing",
            name="is_fixed_price",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="listing",
            name="allow_offers",
            field=models.BooleanField(default=True),
        ),
    ]