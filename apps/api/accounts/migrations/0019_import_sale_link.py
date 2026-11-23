from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0018_notification_inbox")]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="import_order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sales",
                to="accounts.importorder",
            ),
        ),
        migrations.AddConstraint(
            model_name="sale",
            constraint=models.UniqueConstraint(
                condition=models.Q(import_order__isnull=False),
                fields=("import_order",),
                name="unique_sale_per_import_order",
            ),
        ),
        migrations.AlterField(
            model_name="importorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("booking_confirmed", "Booking Confirmed"),
                    ("lc_opened", "LC Opened"),
                    ("bl_issued", "BL Issued"),
                    ("shipping", "Shipping"),
                    ("arrived", "Arrived"),
                    ("customs_clearance", "Customs Clearance"),
                    ("ready_for_collection", "Ready for Collection"),
                    ("handed_over", "Handed Over"),
                ],
                db_index=True,
                default="new",
                max_length=32,
            ),
        ),
    ]
