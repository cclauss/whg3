# Generated by Django 2.2.13 on 2020-07-14 22:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0020_auto_20200422_1317'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='creator',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='dataset',
            name='webpage',
            field=models.URLField(blank=True, null=True),
        ),
    ]
