# Generated by Django 4.1.7 on 2024-01-23 09:46

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0007_tileset'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='tileset',
            options={'managed': True},
        ),
        migrations.AlterModelTable(
            name='tileset',
            table='tilesets',
        ),
    ]