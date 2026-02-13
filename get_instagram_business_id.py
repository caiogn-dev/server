#!/usr/bin/env python
"""
Buscar Instagram Business Account ID correto da página.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.instagram.models import InstagramAccount
import requests

def get_instagram_business_id():
    """Busca o Instagram Business Account ID da página."""
    
    print("=" * 80)
    print("BUSCANDO INSTAGRAM BUSINESS ACCOUNT ID")
    print("=" * 80)
    
    # 1. Buscar conta
    account = InstagramAccount.objects.filter(username='user_25933691062929660').first()
    
    if not account:
        print("❌ Conta não encontrada!")
        return
    
    print(f"\n✅ Conta encontrada: {account.username}")
    print(f"   ID: {account.id}")
    print(f"   Facebook Page ID: {account.facebook_page_id}")
    print(f"   Instagram Account ID (atual): {account.instagram_account_id}")
    
    token = account.access_token
    
    # 2. Buscar Instagram Business Account da página
    print("\n" + "=" * 80)
    print("BUSCANDO INSTAGRAM BUSINESS ACCOUNT DA PÁGINA")
    print("=" * 80)
    
    page_url = f"https://graph.facebook.com/v21.0/{account.facebook_page_id}"
    params = {
        'fields': 'id,name,instagram_business_account{id,username,name,profile_picture_url}',
        'access_token': token
    }
    
    try:
        resp = requests.get(page_url, params=params)
        print(f"\nStatus: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Página: {data.get('name')}")
            print(f"   ID: {data.get('id')}")
            
            ig_account = data.get('instagram_business_account')
            if ig_account:
                print(f"\n✅ Instagram Business Account encontrado:")
                print(f"   ID: {ig_account.get('id')}")
                print(f"   Username: {ig_account.get('username')}")
                print(f"   Nome: {ig_account.get('name')}")
                
                # 3. Atualizar no banco
                ig_id = ig_account.get('id')
                if ig_id and ig_id != account.instagram_account_id:
                    print(f"\n⚠️ ID DIFERENTE DO BANCO!")
                    print(f"   Banco: {account.instagram_account_id}")
                    print(f"   Correto: {ig_id}")
                    
                    resposta = input("\nDeseja atualizar o ID no banco? (s/n): ")
                    if resposta.lower() == 's':
                        account.instagram_account_id = ig_id
                        account.username = ig_account.get('username') or account.username
                        account.save()
                        print(f"✅ ID atualizado no banco!")
                    else:
                        print("❌ ID não atualizado.")
                elif ig_id == account.instagram_account_id:
                    print(f"\n✅ ID no banco está correto!")
            else:
                print(f"\n❌ Instagram Business Account não encontrado na página!")
                print(f"   Verifique se a página está conectada a uma conta do Instagram.")
        else:
            print(f"❌ Erro: {resp.status_code}")
            print(f"   Response: {resp.text}")
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    get_instagram_business_id()
