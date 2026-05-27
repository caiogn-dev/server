from django.db import models


class MessageContext(models.Model):
    """
    Contexto de mensagens — para reply e encaminhamento.
    """

    message = models.OneToOneField(
        'whatsapp.Message',
        on_delete=models.CASCADE,
        related_name='context',
        verbose_name='Mensagem',
        null=True,
        blank=True,
    )

    quoted_message_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID Mensagem Citada',
    )

    quoted_message_content = models.TextField(
        blank=True,
        null=True,
        verbose_name='Conteúdo da Mensagem Citada',
    )

    quoted_message_type = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Tipo da Mensagem Citada',
    )

    quoted_sender_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='ID do Remetente Original',
    )

    is_forwarded = models.BooleanField(default=False, verbose_name='É Encaminhada')
    forwarded_count = models.PositiveIntegerField(default=0, verbose_name='Número de Encaminhamentos')
    is_frequently_forwarded = models.BooleanField(default=False, verbose_name='Frequentemente Encaminhada')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        app_label = 'whatsapp'
        db_table = 'whatsapp_message_contexts'
        verbose_name = 'Contexto de Mensagem'
        verbose_name_plural = 'Contextos de Mensagens'
        indexes = [
            models.Index(fields=['quoted_message_id'], name='wh_msgctx_quoted_id_idx'),
            models.Index(fields=['is_forwarded'], name='wh_msgctx_is_forwarded_idx'),
            models.Index(fields=['is_frequently_forwarded'], name='wh_msgctx_is_freq_fwd_idx'),
        ]

    def __str__(self):
        if self.is_forwarded:
            return "Forwarded message (x%s)" % self.forwarded_count
        elif self.quoted_message_id:
            return "Reply to %s" % self.quoted_message_id
        return "Message context"

    def set_quoted_message(self, message_id, content, message_type, sender_id):
        self.quoted_message_id = message_id
        self.quoted_message_content = content
        self.quoted_message_type = message_type
        self.quoted_sender_id = sender_id
        self.save()

    def mark_as_forwarded(self, count=1):
        self.is_forwarded = True
        self.forwarded_count = count
        if count >= 5:
            self.is_frequently_forwarded = True
        self.save()
