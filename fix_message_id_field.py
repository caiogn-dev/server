#!/usr/bin/env python
"""
Alterar tamanho do campo instagram_message_id.
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.db import connection

print("Alterando tamanho do campo instagram_message_id...")

with connection.cursor() as cursor:
    # Alterar tamanho do campo
    cursor.execute("""
        ALTER TABLE instagram_messages 
        ALTER COLUMN instagram_message_id TYPE VARCHAR(255);
    """)
    
    print("✅ Campo alterado com sucesso!")
    
    # Verificar
    cursor.execute("""
        SELECT column_name, data_type, character_maximum_length 
        FROM information_schema.columns 
        WHERE table_name = 'instagram_messages' 
        AND column_name = 'instagram_message_id';
    """)
    
    row = cursor.fetchone()
    print(f"\nCampo: {row[0]}")
    print(f"Tipo: {row[1]}")
    print(f"Tamanho máximo: {row[2]}")
