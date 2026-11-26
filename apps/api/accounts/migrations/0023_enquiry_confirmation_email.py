from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0022_handoverdocumentreceipt")]

    operations = [
        migrations.AddField(
            model_name="enquiry",
            name="confirmation_email_status",
            field=models.CharField(blank=True, choices=[("no_email", "No email address"), ("queued", "Queued"), ("sending", "Sending"), ("sent", "Accepted by mail service"), ("failed", "Failed")], default="", max_length=16),
        ),
        migrations.AddField(
            model_name="enquiry",
            name="confirmation_email_schedule",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="enquiry",
            name="confirmation_email_is_update",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="enquiry",
            name="confirmation_email_recipient",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="enquiry",
            name="confirmation_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="enquiry",
            name="confirmation_email_error",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
