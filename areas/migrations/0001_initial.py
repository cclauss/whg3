# Generated by Django 4.1.7 on 2023-04-09 14:50

import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Area',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('ccodes', 'Country codes'), ('drawn', 'User drawn'), ('predefined', 'World Regions'), ('search', 'Region/Polity record'), ('copied', 'CopyPasted GeoJSON')], max_length=20)),
                ('title', models.CharField(max_length=255)),
                ('description', models.CharField(max_length=2044)),
                ('ccodes', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=2), blank=True, null=True, size=None)),
                ('geojson', models.JSONField(blank=True, null=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'areas',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='Country',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tgnid', models.IntegerField(blank=True, null=True, verbose_name='Getty TGN id')),
                ('tgnlabel', models.CharField(blank=True, max_length=255, null=True, verbose_name='Getty TGN preferred name')),
                ('iso', models.CharField(max_length=2, verbose_name='2-character code')),
                ('gnlabel', models.CharField(max_length=255, verbose_name='geonames label')),
                ('geonameid', models.IntegerField(verbose_name='geonames id')),
                ('un', models.CharField(blank=True, max_length=3, null=True, verbose_name='UN name')),
                ('variants', models.CharField(blank=True, max_length=512, null=True)),
                ('mpoly', django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326)),
            ],
            options={
                'db_table': 'countries',
                'managed': True,
            },
        ),
    ]
