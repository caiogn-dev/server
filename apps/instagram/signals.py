# Instagram Signals
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


# Signals para processamento assíncrono podem ser adicionados aqui