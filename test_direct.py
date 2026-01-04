import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")
dbname = os.getenv("DB_NAME")

print(f"Conectando como:")
print(f"  User: {user}")
print(f"  Host: {host}:{port}")
print(f"  Database: {dbname}")
print()

try:
    # Teste 1: Conexão com parametros separados
    print("Teste 1: Conexão com parâmetros separados")
    conn1 = psycopg2.connect(
        user=user,
        password=password,
        host=host,
        port=port,
        dbname=dbname
    )
    print("✅ Sucesso!")
    conn1.close()
    
except Exception as e:
    print(f"❌ Falhou: {e}")
