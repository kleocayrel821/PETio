from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0005_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaserequest",
            name="canceled_reason",
            field=models.TextField(blank=True),
        ),
    ]