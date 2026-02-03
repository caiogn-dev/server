#!/usr/bin/env python3
"""
Atualizar localização da loja Pastita
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

from apps.stores.models import Store

def update_store_location():
    try:
        store = Store.objects.get(slug='pastita')
        
        print(f"Loja encontrada: {store.name}")
        print(f"Localização atual: Lat={store.latitude}, Lng={store.longitude}")
        
        # Atualizar com coordenadas de Palmas-TO
        store.latitude = -10.1853353
        store.longitude = -48.3036316
        store.address = "Q. 112 Sul Rua SR 1, conj. 06 lote 04 - Plano Diretor Sul"
        store.city = "Palmas"
        store.state = "TO"
        store.zip_code = "77020-170"
        store.country = "BR"
        
        store.save()
        
        print(f"\n✅ Localização atualizada!")
        print(f"   Lat: {store.latitude}")
        print(f"   Lng: {store.longitude}")
        print(f"   Endereço: {store.address}, {store.city} - {store.state}")
        
    except Store.DoesNotExist:
        print("❌ Loja 'pastita' não encontrada")
        return False
    
    return True

if __name__ == '__main__':
    update_store_location()
