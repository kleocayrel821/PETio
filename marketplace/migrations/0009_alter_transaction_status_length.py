from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0008_transaction_payment_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="status",
            field=models.CharField(max_length=20, choices=[
                ("proposed", "Proposed"),
                ("confirmed", "Confirmed"),
                ("awaiting_payment", "Awaiting Payment"),
                ("paid", "Paid"),
                ("completed", "Completed"),
                ("canceled", "Canceled"),
            ], default="proposed", db_index=True),
        ),
    ]