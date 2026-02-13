#!/usr/bin/env python
"""
Teste completo de envio de mensagem Instagram.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount
from apps.instagram.services.instagram_api import InstagramAPIService
import requests

def test_instagram_message():
    """Testa envio de mensagem Instagram."""
    
    print("=" * 80)
    print("TESTE COMPLETO DE ENVIO DE MENSAGEM INSTAGRAM")
    print("=" * 80)
    
    # 1. Buscar conta
    account = InstagramAccount.objects.filter(username='pastita.reserva').first()
    
    if not account:
        print("❌ Conta não encontrada!")
        return
    
    print(f"\n✅ Conta encontrada: {account.username}")
    print(f"   ID: {account.id}")
    print(f"   Facebook Page ID: {account.facebook_page_id}")
    print(f"   Instagram Account ID: {account.instagram_account_id}")
    
    # 2. Verificar token
    token = account.access_token
    if not token:
        print("❌ Token não encontrado!")
        return
    
    print(f"\n✅ Token encontrado (primeiros 50 chars): {token[:50]}...")
    
    # 3. Testar permissões do token
    print("\n" + "=" * 80)
    print("TESTANDO PERMISSÕES DO TOKEN")
    print("=" * 80)
    
    permissions_url = f"https://graph.facebook.com/v21.0/me/permissions?access_token={token}"
    
    try:
        resp = requests.get(permissions_url)
        if resp.status_code == 200:
            perms_data = resp.json()
            granted_perms = [p['permission'] for p in perms_data.get('data', []) if p['status'] == 'granted']
            print(f"\n✅ Permissões ativas ({len(granted_perms)}):")
            for perm in sorted(granted_perms):
                print(f"   - {perm}")
        else:
            print(f"❌ Erro ao buscar permissões: {resp.status_code}")
            print(f"   Response: {resp.text}")
    except Exception as e:
        print(f"❌ Erro ao testar permissões: {e}")
    
    # 4. Testar info da página
    print("\n" + "=" * 80)
    print("TESTANDO INFO DA PÁGINA")
    print("=" * 80)
    
    page_url = f"https://graph.facebook.com/v21.0/{account.facebook_page_id}?fields=id,name,instagram_business_account&access_token={token}"
    
    try:
        resp = requests.get(page_url)
        print(f"\nStatus: {resp.status_code}")
        if resp.status_code == 200:
            page_data = resp.json()
            print(f"✅ Página: {page_data.get('name')}")
            print(f"   ID: {page_data.get('id')}")
            print(f"   Instagram Business Account: {page_data.get('instagram_business_account', {}).get('id', 'N/A')}")
        else:
            print(f"❌ Erro: {resp.text}")
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    # 5. Testar envio de mensagem
    print("\n" + "=" * 80)
    print("TESTANDO ENVIO DE MENSAGEM")
    print("=" * 80)
    
    recipient_id = "1434322381572508"  # ID do destinatário de teste (gracolandi4)
    
    print(f"\nDestinatário: {recipient_id}")
    print(f"Endpoint: https://graph.facebook.com/v21.0/{account.facebook_page_id}/messages")
    
    # Criar serviço API
    api_service = InstagramAPIService(account)
    
    try:
        # Tentar enviar mensagem
        result = api_service.send_text_message(
            recipient_id=recipient_id,
            text="🧪 Teste de envio via API - " + str(os.getpid())
        )
        
        print(f"\n✅ MENSAGEM ENVIADA COM SUCESSO!")
        print(f"   Resposta: {result}")
        
    except Exception as e:
        print(f"\n❌ Erro ao enviar mensagem:")
        print(f"   Tipo: {type(e).__name__}")
        print(f"   Mensagem: {str(e)}")
        
        # Verificar se é erro de API
        if hasattr(e, 'code'):
            print(f"   Código: {e.code}")
        if hasattr(e, 'subcode'):
            print(f"   Subcode: {e.subcode}")
        if hasattr(e, 'details'):
            print(f"   Detalhes: {e.details}")
        
        # Explicações comuns
        error_str = str(e).lower()
        if 'code 10' in error_str or 'code: 10' in error_str:
            print("\n💡 CAUSA PROVÁVEL:")
            print("   Esta mensagem foi enviada fora da janela permitida de 24 horas.")
            print("   SOLUÇÃO: Peça para alguém enviar uma mensagem no Instagram AGORA")
            print("   e tente responder dentro de 24 horas.")
        elif 'code 1' in error_str or 'code: 1' in error_str:
            print("\n💡 CAUSA PROVÁVEL:")
            print("   Token inválido ou sem permissões corretas.")
            print("   Verifique se o token tem as permissões:")
            print("   - instagram_manage_messages")
            print("   - pages_messaging")
        elif 'code 100' in error_str or 'code: 100' in error_str:
            print("\n💡 CAUSA PROVÁVEL:")
            print("   Parâmetro inválido ou recipient_id incorreto.")
    
    print("\n" + "=" * 80)
    print("FIM DO TESTE")
    print("=" * 80)

if __name__ == '__main__':
    test_instagram_message()
