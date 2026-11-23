from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0019_import_sale_link")]

    operations = [
        migrations.AddField(
            model_name="enquiry",
            name="vehicle_description",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
