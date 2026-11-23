from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0020_enquiry_vehicle_description")]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="finance_terms",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
