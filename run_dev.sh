#!/bin/bash
# Script para rodar o servidor Django localmente na porta 3010

cd /home/graco/WORK/server2

# Exportar variáveis de ambiente para desenvolvimento
export DEBUG=True
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,dev.painel.pastita.com.br
export PORT=3010

echo "🚀 Iniciando servidor Django na porta $PORT..."
echo "📍 Acesse: http://localhost:$PORT"
echo "🌐 Ou: http://dev.painel.pastita.com.br (após configurar túnel)"
echo ""

# Rodar o servidor
python manage.py runserver 0.0.0.0:$PORT
