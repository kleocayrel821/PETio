from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0007_purchase_request_negotiation_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="payment_method",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("cash", "Cash"),
                    ("bank_transfer", "Bank Transfer"),
                    ("other", "Other"),
                ],
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="amount_paid",
            field=models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="transaction",
            name="payment_proof",
            field=models.FileField(upload_to="payments/%Y/%m/", null=True, blank=True),
        ),
    ]