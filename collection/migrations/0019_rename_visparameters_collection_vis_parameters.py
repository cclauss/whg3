# Generated by Django 4.1.7 on 2023-12-12 12:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('collection', '0018_collection_visparameters'),
    ]

    operations = [
        migrations.RenameField(
            model_name='collection',
            old_name='visParameters',
            new_name='vis_parameters',
        ),
    ]
