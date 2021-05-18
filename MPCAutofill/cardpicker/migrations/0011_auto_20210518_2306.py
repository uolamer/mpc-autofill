# Generated by Django 3.2.3 on 2021-05-18 13:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cardpicker', '0010_auto_20210517_2034'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='source',
            name='drivelink',
        ),
        migrations.RemoveField(
            model_name='source',
            name='drivename',
        ),
        migrations.AddField(
            model_name='source',
            name='drive_id',
            field=models.CharField(default='', max_length=200),
            preserve_default=False,
        ),
    ]
