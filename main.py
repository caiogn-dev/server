import psycopg2
from dotenv import load_dotenv
from urllib.parse import quote
import os

# Load environment variables from .env
load_dotenv()

# Fetch variables from .env
user = os.getenv("user")
password = os.getenv("password")
host = os.getenv("host")
port = os.getenv("port")
dbname = os.getenv("dbname")

print(f"Tentando conectar com:")
print(f"  User: {user}")
print(f"  Host: {host}")
print(f"  Port: {port}")
print(f"  Database: {dbname}")
print()

# URL encode the password due to special characters
encoded_password = quote(password, safe='')

# Build the connection URI with proper escaping
DATABASE_URL = f"postgresql://{user}:{encoded_password}@{host}:{port}/{dbname}"

# Connect to the database
try:
    connection = psycopg2.connect(DATABASE_URL)
    print("✅ Conexão bem-sucedida!")
    
    # Create a cursor to execute SQL queries
    cursor = connection.cursor()
    
    # Example query
    cursor.execute("SELECT NOW();")
    result = cursor.fetchone()
    print("Hora atual:", result)

    # Close the cursor and connection
    cursor.close()
    connection.close()
    print("✅ Conexão fechada.")

except Exception as e:
    print(f"❌ Falha na conexão: {e}")
