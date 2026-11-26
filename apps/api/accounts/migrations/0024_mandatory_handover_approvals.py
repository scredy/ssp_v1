from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def move_legacy_review_queue_to_md(apps, schema_editor):
    Handover = apps.get_model("accounts", "Handover")
    # The old state only meant “submitted for review”; it did not identify an
    # MD/CEO decision. Preserve the pending work at the first approval stage.
    Handover.objects.filter(status="ready_for_review").update(status="pending_md_review")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0023_enquiry_confirmation_email")]

    operations = [
        migrations.AddField(
            model_name="handover",
            name="md_approved_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="md_approved_handovers", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="handover",
            name="md_approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="handover",
            name="ceo_approved_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="ceo_approved_handovers", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="handover",
            name="ceo_approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="handover",
            name="status",
            field=models.CharField(choices=[("preparing", "Preparing"), ("pending_md_review", "Pending MD Review"),
                ("pending_ceo_approval", "Pending CEO Approval"), ("ceo_approved", "CEO Approved"), ("finalized", "Finalized")],
                db_index=True, default="preparing", max_length=20),
        ),
        migrations.CreateModel(
            name="HandoverApproval",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reviewer_role", models.CharField(max_length=16)),
                ("decision", models.CharField(choices=[("submitted_for_md", "Submitted for MD review"),
                    ("md_approved", "Approved by MD"), ("ceo_approved", "Approved by CEO"),
                    ("md_returned", "Returned to Staff"), ("ceo_returned", "Returned to MD"),
                    ("finalized", "Finalized by MD")], max_length=32)),
                ("status_before", models.CharField(max_length=20)),
                ("status_after", models.CharField(max_length=20)),
                ("comments", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("handover", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name="approval_history", to="accounts.handover")),
                ("reviewer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name="handover_approval_decisions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at", "pk"]},
        ),
        migrations.RunPython(move_legacy_review_queue_to_md, migrations.RunPython.noop),
    ]
