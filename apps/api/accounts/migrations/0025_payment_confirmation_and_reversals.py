from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0024_mandatory_handover_approvals")]

    operations = [
        # Existing payments predate payment_type. Preserve that uncertainty rather
        # than classifying every historical payment as a partial payment.
        migrations.AddField(
            model_name="payment", name="payment_type",
            field=models.CharField(default="unspecified", max_length=24),
        ),
        migrations.AlterField(
            model_name="payment", name="status",
            field=models.CharField(choices=[("pending", "Pending"), ("verified", "Verified"), ("rejected", "Rejected"), ("reversed", "Reversed")], db_index=True, default="pending", max_length=10),
        ),
        migrations.AlterField(
            model_name="payment", name="payment_type",
            field=models.CharField(choices=[("unspecified", "Unspecified (historical)"), ("advance", "Advance"), ("partial", "Partial Payment"), ("final", "Final Payment"), ("finance_settlement", "Finance Settlement")], default="partial", max_length=24),
        ),
        migrations.AddField(model_name="payment", name="idempotency_key", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField(model_name="payment", name="funds_cleared", field=models.BooleanField(default=False)),
        migrations.AddConstraint(model_name="payment", constraint=models.UniqueConstraint(condition=~models.Q(idempotency_key=""), fields=("idempotency_key",), name="payment_idempotency_key_unique")),
        migrations.AddField(model_name="payment", name="reversal_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="payment", name="reversed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="payment", name="reversed_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reversed_payments", to=settings.AUTH_USER_MODEL)),
    ]
