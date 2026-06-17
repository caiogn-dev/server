from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0036_alter_storepayment_payer_document'),
    ]

    operations = [
        migrations.AddField(
            model_name='storecategory',
            name='is_builder_group',
            field=models.BooleanField(
                default=False,
                help_text='Categoria usada apenas no Salad Builder; não aparece como seção do cardápio.',
            ),
        ),
    ]
