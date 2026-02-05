#!/usr/bin/env python
"""Check Instagram token permissions"""
import os
import sys
import django
import requests

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount

account = InstagramAccount.objects.first()
if not account:
    print("❌ Nenhuma conta Instagram encontrada")
    sys.exit(1)

print(f"\n{'='*70}")
print(f"VERIFICAÇÃO DE PERMISSÕES - {account.username}")
print(f"{'='*70}\n")

token = account.access_token
print(f"Token: {token[:30]}...")
print(f"Page ID: {account.facebook_page_id}")
print(f"Instagram ID: {account.instagram_account_id}\n")

# Check permissions
try:
    response = requests.get(
        'https://graph.facebook.com/v21.0/me/permissions',
        params={'access_token': token},
        timeout=10
    )
    
    if response.status_code != 200:
        print(f"❌ Erro ao buscar permissões: {response.json()}")
        print("\n⚠️  PROBLEMA: Este é um Page Access Token, não um User Access Token")
        print("   A rota /me/permissions só funciona com User Access Token\n")
        sys.exit(1)
    
    perms_data = response.json().get('data', [])
    granted = [p['permission'] for p in perms_data if p['status'] == 'granted']
    
    print("✓ Permissões ativas no token:")
    for perm in sorted(granted):
        print(f"  • {perm}")
    
    # Check required permissions
    print(f"\n{'-'*70}")
    print("PERMISSÕES NECESSÁRIAS PARA INSTAGRAM MESSAGING:")
    print(f"{'-'*70}\n")
    
    required = {
        'instagram_manage_messages': 'Gerenciar mensagens do Instagram',
        'instagram_business_manage_messages': 'Gerenciar mensagens (Business)',
        'pages_messaging': 'Enviar mensagens pela página',
        'pages_manage_metadata': 'Gerenciar metadados da página',
        'instagram_basic': 'Acesso básico ao Instagram',
    }
    
    all_ok = True
    for perm, desc in required.items():
        if perm in granted:
            print(f"✓ {perm:<40} {desc}")
        else:
            print(f"✗ {perm:<40} {desc} ❌ FALTANDO")
            all_ok = False
    
    if all_ok:
        print(f"\n✅ Todas as permissões necessárias estão ativas!")
    else:
        print(f"\n❌ Algumas permissões estão faltando!")
        print("\nPara adicionar permissões:")
        print("1. Acesse: https://developers.facebook.com/tools/explorer/")
        print("2. Selecione seu app")
        print("3. Clique em 'Get Token' → 'Get Page Access Token'")
        print("4. Marque TODAS as permissões necessárias")
        print("5. Copie o novo token e atualize no banco de dados")
    
except Exception as e:
    print(f"❌ Erro: {e}")
    print("\n⚠️  POSSÍVEL PROBLEMA: Page Access Token vs User Access Token")
    print("   Para verificar permissões, você precisa:")
    print("   1. Usar um User Access Token OU")
    print("   2. Verificar permissões direto no Facebook App Dashboard")

print(f"\n{'='*70}")
print("COMO GERAR NOVO TOKEN COM TODAS AS PERMISSÕES:")
print(f"{'='*70}\n")
print("1. Acesse: https://developers.facebook.com/tools/explorer/")
print("2. Selecione seu app na lista")
print("3. Clique em 'Get Token' → 'Get Page Access Token'")
print("4. Escolha a página conectada ao Instagram")
print("5. Marque as permissões:")
print("   □ instagram_manage_messages")
print("   □ instagram_business_manage_messages")
print("   □ pages_messaging")
print("   □ pages_manage_metadata")
print("   □ pages_read_engagement")
print("   □ instagram_basic")
print("6. Clique em 'Generate Access Token'")
print("7. Copie o token e atualize no banco:\n")
print(f"   account = InstagramAccount.objects.get(id='{account.id}')")
print("   account.access_token = 'COLE_AQUI_O_NOVO_TOKEN'")
print("   account.save()")
print("\n")
