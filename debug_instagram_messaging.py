#!/usr/bin/env python
"""
Script de diagnóstico para Instagram Messaging API
"""
import os
import sys
import django
import requests

# Setup Django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount

def diagnose_account(account_id=None):
    if account_id:
        account = InstagramAccount.objects.get(id=account_id)
    else:
        account = InstagramAccount.objects.first()
    
    if not account:
        print("❌ Nenhuma conta do Instagram encontrada no banco de dados")
        return
    
    print("\n" + "="*60)
    print("DIAGNÓSTICO: Instagram Account")
    print("="*60)
    print(f"ID: {account.id}")
    print(f"Username: {account.username}")
    print(f"Instagram Account ID: {account.instagram_account_id}")
    print(f"Facebook Page ID: {account.facebook_page_id or 'NÃO CONFIGURADO ❌'}")
    print(f"Token Type: {'IGAA Token' if account.access_token.startswith('IGAA') else 'Page Access Token'}")
    print(f"Token (primeiros 20 chars): {account.access_token[:20]}...")
    print(f"Status: {account.status}")
    
    # Test token validity
    print("\n" + "-"*60)
    print("Testando Token...")
    print("-"*60)
    
    token = account.access_token
    
    # Test 1: Get account info
    try:
        response = requests.get(
            f"https://graph.facebook.com/v21.0/{account.instagram_account_id}",
            params={'access_token': token, 'fields': 'id,username'},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Token válido - Account Info OK")
            print(f"  Username: {data.get('username')}")
        else:
            error = response.json()
            print(f"✗ Erro ao buscar account info:")
            print(f"  {error}")
    except Exception as e:
        print(f"✗ Erro: {e}")
    
    # Test 2: Check permissions
    try:
        response = requests.get(
            "https://graph.facebook.com/v21.0/me/permissions",
            params={'access_token': token},
            timeout=10
        )
        if response.status_code == 200:
            perms = response.json().get('data', [])
            print("\nPermissões do Token:")
            required_perms = [
                'instagram_basic',
                'instagram_manage_messages',
                'pages_messaging',
                'pages_manage_metadata'
            ]
            
            granted_perms = [p['permission'] for p in perms if p['status'] == 'granted']
            
            for req_perm in required_perms:
                if req_perm in granted_perms:
                    print(f"  ✓ {req_perm}: granted")
                else:
                    print(f"  ✗ {req_perm}: NOT GRANTED ❌")
            
            print("\nOutras permissões:")
            for perm in perms:
                if perm['permission'] not in required_perms:
                    status = "✓" if perm['status'] == 'granted' else "✗"
                    print(f"  {status} {perm['permission']}: {perm['status']}")
        else:
            error = response.json()
            print(f"✗ Erro ao buscar permissões:")
            print(f"  {error}")
    except Exception as e:
        print(f"✗ Erro: {e}")
    
    # Test 3: Check if Page ID is configured
    if not account.facebook_page_id:
        print("\n⚠️  ATENÇÃO: facebook_page_id não configurado!")
        print("   Para enviar mensagens, você precisa configurar o Page ID")
        print("   da página do Facebook conectada ao Instagram.")
        
        # Try to find the page ID
        try:
            response = requests.get(
                f"https://graph.facebook.com/v21.0/{account.instagram_account_id}",
                params={'access_token': token, 'fields': 'id,username,page'},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if 'page' in data:
                    page_id = data['page'].get('id')
                    print(f"\n✓ Page ID encontrado: {page_id}")
                    print(f"   Execute para configurar:")
                    print(f"   account = InstagramAccount.objects.get(id={account.id})")
                    print(f"   account.facebook_page_id = '{page_id}'")
                    print(f"   account.save()")
        except Exception as e:
            pass
    else:
        print(f"\n✓ facebook_page_id configurado: {account.facebook_page_id}")
        
        # Test Page endpoint
        try:
            response = requests.get(
                f"https://graph.facebook.com/v21.0/{account.facebook_page_id}",
                params={'access_token': token, 'fields': 'id,name'},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                print(f"  Page Name: {data.get('name')}")
            else:
                error = response.json()
                print(f"  ⚠️ Erro ao acessar Page: {error}")
        except Exception as e:
            print(f"  ⚠️ Erro: {e}")
    
    print("\n" + "="*60)
    print("Recomendações:")
    print("="*60)
    
    recommendations = []
    
    if account.access_token.startswith('IGAA'):
        recommendations.append("❌ Você está usando IGAA Token - Para enviar mensagens, troque por Page Access Token")
    else:
        recommendations.append("✓ Token type correto (Page Access Token)")
    
    if not account.facebook_page_id:
        recommendations.append("❌ Configure o facebook_page_id")
    else:
        recommendations.append("✓ facebook_page_id configurado")
    
    for rec in recommendations:
        print(rec)
    
    print("\n" + "="*60)
    print("Como obter Page Access Token:")
    print("="*60)
    print("1. Acesse: https://developers.facebook.com/tools/explorer/")
    print("2. Selecione seu app")
    print("3. Clique em 'Get Token' → 'Get Page Access Token'")
    print("4. Escolha a página conectada ao Instagram")
    print("5. Copie o token e atualize:")
    print(f"\n   account = InstagramAccount.objects.get(id={account.id})")
    print("   account.access_token = 'COLE_O_TOKEN_AQUI'")
    print("   account.save()")
    
    print("\n")

if __name__ == '__main__':
    account_id = sys.argv[1] if len(sys.argv) > 1 else None
    diagnose_account(account_id)
