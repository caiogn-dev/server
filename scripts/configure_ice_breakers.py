#!/usr/bin/env python
"""
Script para configurar Ice Breakers no Instagram.
Ice Breakers permitem que usuários iniciem conversas com perguntas predefinidas.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount
from apps.instagram.services.instagram_api import InstagramAPIService, InstagramAPIError


def configure_ice_breakers(account_id: str):
    """Configura Ice Breakers para uma conta do Instagram."""
    print(f"\n{'='*60}")
    print(f"CONFIGURANDO ICE BREAKERS")
    print(f"{'='*60}\n")
    
    try:
        account = InstagramAccount.objects.get(id=account_id)
    except InstagramAccount.DoesNotExist:
        print(f"❌ Conta não encontrada: {account_id}")
        return
    
    print(f"✓ Conta: {account.name} (@{account.username})")
    print(f"✓ Instagram ID: {account.instagram_account_id}")
    
    # Ice Breakers predefinidos para loja de massas
    ice_breakers = [
        {
            'question': '🍝 Ver cardápio',
            'payload': 'GET_MENU'
        },
        {
            'question': '📦 Fazer pedido',
            'payload': 'NEW_ORDER'
        },
        {
            'question': '📍 Endereço e horário',
            'payload': 'LOCATION_HOURS'
        },
        {
            'question': '💬 Falar com atendente',
            'payload': 'TALK_TO_HUMAN'
        }
    ]
    
    print(f"\n{'─'*60}")
    print("Ice Breakers que serão configurados:")
    print(f"{'─'*60}")
    for i, ib in enumerate(ice_breakers, 1):
        print(f"{i}. {ib['question']} → {ib['payload']}")
    
    confirm = input("\nDeseja continuar? (s/N): ").strip().lower()
    if confirm != 's':
        print("❌ Operação cancelada.")
        return
    
    print(f"\n{'─'*60}")
    print("Enviando para Instagram API...")
    print(f"{'─'*60}")
    
    try:
        api = InstagramAPIService(account)
        result = api.set_ice_breakers(ice_breakers)
        
        # Salvar no metadata
        account.metadata = account.metadata or {}
        account.metadata['ice_breakers'] = ice_breakers
        account.save(update_fields=['metadata', 'updated_at'])
        
        print(f"\n✅ Ice Breakers configurados com sucesso!")
        print(f"\nAgora os usuários verão estas opções ao iniciar uma conversa no Instagram.")
        print(f"\nResposta da API:")
        print(result)
        
    except InstagramAPIError as e:
        print(f"\n❌ Erro ao configurar Ice Breakers: {e}")
        print(f"   Code: {e.code}, Subcode: {e.subcode}")
        print(f"\nPossíveis causas:")
        print(f"- Token sem permissões necessárias")
        print(f"- Ice Breakers não habilitados para esta conta")
        print(f"- Conta não é Professional Account")
    
    print(f"\n{'='*60}\n")


if __name__ == '__main__':
    # List all accounts
    accounts = InstagramAccount.objects.all()
    
    if not accounts:
        print("❌ Nenhuma conta do Instagram encontrada.")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print("CONTAS DISPONÍVEIS")
    print(f"{'='*60}\n")
    
    for i, acc in enumerate(accounts, 1):
        print(f"{i}. {acc.name} (@{acc.username}) - ID: {acc.id}")
    
    print()
    
    if len(sys.argv) > 1:
        account_id = sys.argv[1]
    else:
        choice = input("Digite o número da conta (ou ID direto): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(accounts):
            account_id = str(accounts[int(choice) - 1].id)
        else:
            account_id = choice
    
    configure_ice_breakers(account_id)
