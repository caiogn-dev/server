from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0005_remove_conversationhandover'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='profile_name_last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='conversation',
            name='profile_picture_file',
            field=models.ImageField(
                blank=True,
                help_text='Locally persisted contact avatar',
                null=True,
                upload_to='whatsapp/profile_pictures/',
            ),
        ),
        migrations.AddField(
            model_name='conversation',
            name='profile_picture_url',
            field=models.URLField(
                blank=True,
                help_text='External/profile avatar URL when available from CRM or linked user profile',
            ),
        ),
        migrations.AddField(
            model_name='conversation',
            name='wa_id',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='WhatsApp user id from webhook contacts[].wa_id',
                max_length=32,
            ),
        ),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(fields=['account', 'wa_id'], name='conversatio_account_ffc757_idx'),
        ),
    ]
