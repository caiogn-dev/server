"""
Script para popular UnifiedUser a partir de conversas existentes

Uso:
    docker exec -it pastita_web python manage.py shell < populate_unified_users.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

from apps.conversations.models import Conversation
from apps.users.models import UnifiedUser
from apps.users.services import UnifiedUserService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def populate_unified_users_from_conversations():
    """
    Cria UnifiedUsers para todas as conversas existentes
    """
    logger.info("=" * 60)
    logger.info("POPULANDO UNIFIED USERS DAS CONVERSAS EXISTENTES")
    logger.info("=" * 60)
    
    # Busca todas as conversas com phone_number
    conversations = Conversation.objects.filter(
        phone_number__isnull=False
    ).exclude(
        phone_number=''
    ).distinct('phone_number')
    
    logger.info(f"Total de conversas únicas encontradas: {conversations.count()}")
    
    created_count = 0
    existing_count = 0
    error_count = 0
    
    for conv in conversations:
        try:
            user, created = UnifiedUser.objects.get_or_create(
                phone_number=conv.phone_number,
                defaults={
                    'name': conv.contact_name or 'Cliente WhatsApp',
                }
            )
            
            if created:
                created_count += 1
                logger.info(f"✅ Criado: {conv.phone_number} - {conv.contact_name or 'Sem nome'}")
            else:
                existing_count += 1
                logger.info(f"⏭️  Já existe: {conv.phone_number}")
                
        except Exception as e:
            error_count += 1
            logger.error(f"❌ Erro ao processar {conv.phone_number}: {e}")
    
    logger.info("=" * 60)
    logger.info("RESUMO:")
    logger.info(f"  Criados: {created_count}")
    logger.info(f"  Já existentes: {existing_count}")
    logger.info(f"  Erros: {error_count}")
    logger.info(f"  Total processado: {created_count + existing_count + error_count}")
    logger.info("=" * 60)
    
    return created_count, existing_count, error_count


def verify_context_for_phone(phone_number: str):
    """
    Verifica o contexto que seria enviado para o agente
    """
    logger.info(f"\n🔍 VERIFICANDO CONTEXTO PARA: {phone_number}")
    logger.info("-" * 60)
    
    context = UnifiedUserService.get_context_for_agent(phone_number)
    
    if context:
        logger.info("Contexto gerado:")
        logger.info(context)
    else:
        logger.warning("⚠️ Nenhum contexto retornado!")
        
        # Verifica se usuário existe
        user = UnifiedUser.objects.filter(phone_number=phone_number).first()
        if user:
            logger.info(f"Usuário existe: {user.name}")
            logger.info(f"get_context_for_agent retornou vazio!")
        else:
            logger.error(f"❌ Usuário não encontrado para {phone_number}")
    
    return context


if __name__ == '__main__':
    # 1. Popula usuários
    created, existing, errors = populate_unified_users_from_conversations()
    
    # 2. Mostra exemplo de contexto (se houver conversas)
    sample_conv = Conversation.objects.filter(phone_number__isnull=False).first()
    if sample_conv:
        verify_context_for_phone(sample_conv.phone_number)
    
    logger.info("\n✅ Script concluído!")
