# Generated by Django 4.1.7 on 2024-01-10 09:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collection', '0023_remove_collection_visparameters_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='collectiongroup',
            name='collaboration',
            field=models.BooleanField(default=False),
        ),
    ]