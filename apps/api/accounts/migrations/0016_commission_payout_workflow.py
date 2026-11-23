import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_commission_ledger"),
    ]

    operations = [
        migrations.AlterField(
            model_name="commissionledgerentry",
            name="status",
            field=models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("paid", "Paid"), ("reversed", "Reversed")], default="pending", max_length=16),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="approved_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="approved_commission_entries", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="paid_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="paid_commission_entries", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="payout_amount_lkr",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="payout_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="payout_reference",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="reversal_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="reversed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="commissionledgerentry",
            name="reversed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reversed_commission_entries", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(
            model_name="commissionledgerentry",
            constraint=models.UniqueConstraint(condition=~models.Q(payout_reference=""), fields=("payout_reference",), name="commission_payout_reference_unique"),
        ),
    ]
