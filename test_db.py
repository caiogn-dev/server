import os
import django
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("📋 Environment variables loaded:")
print(f"  DB_USER from env: {os.getenv('DB_USER')}")
print(f"  DB_PASSWORD from env: {os.getenv('DB_PASSWORD')[:5]}***")
print(f"  DB_HOST from env: {os.getenv('DB_HOST')}")
print()

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.settings')
django.setup()

from django.db import connection

try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT NOW();")
        result = cursor.fetchone()
        print("✅ Django connection successful!")
        print(f"   Database time: {result[0]}")
        
        # Check database connection settings
        print("\n📊 Connection Settings:")
        print(f"   Engine: {connection.settings_dict['ENGINE']}")
        print(f"   Name: {connection.settings_dict['NAME']}")
        print(f"   User: {connection.settings_dict['USER']}")
        print(f"   Host: {connection.settings_dict['HOST']}")
        print(f"   Port: {connection.settings_dict['PORT']}")
        
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print(f"\n📊 Connection Settings from Django:")
    print(f"   Engine: {connection.settings_dict['ENGINE']}")
    print(f"   Name: {connection.settings_dict['NAME']}")
    print(f"   User: {connection.settings_dict['USER']}")
    print(f"   Host: {connection.settings_dict['HOST']}")
    print(f"   Port: {connection.settings_dict['PORT']}")

