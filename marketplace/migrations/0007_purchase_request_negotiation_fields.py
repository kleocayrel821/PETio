from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0006_purchase_request_canceled_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaserequest",
            name="offer_price",
            field=models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="purchaserequest",
            name="quantity",
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="purchaserequest",
            name="counter_offer",
            field=models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True),
        ),
    ]