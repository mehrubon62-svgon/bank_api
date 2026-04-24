import uuid

from django.db import migrations


def populate_public_ids(apps, schema_editor):
    model_names = ['Account', 'Card', 'Credit', 'Deposit', 'Transaction']
    for model_name in model_names:
        model = apps.get_model('bank_app', model_name)
        for obj in model.objects.filter(public_id__isnull=True).iterator():
            obj.public_id = uuid.uuid4()
            obj.save(update_fields=['public_id'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bank_app', '0003_account_public_id_card_public_id_credit_public_id_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_public_ids, noop_reverse),
    ]
