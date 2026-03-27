#!/usr/bin/env python3
"""
Script para criar/atualizar o Agent IA (Kimi).

Uso:
    docker exec -it pastita_web python create_admin_and_store.py

    Com argumentos personalizados:
    docker exec -it pastita_web python create_admin_and_store.py --agent-name="Assistente" --agent-api-key="SUA_CHAVE"
"""
import os
import sys
import argparse
import secrets
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
sys.path.insert(0, '/app')
django.setup()

from django.db import transaction
from apps.agents.models import Agent


# ============================================================================
# CONFIGURAÇÕES PADRÃO
# ============================================================================

DEFAULT_CONFIG = {
    # Agent IA
    'agent_name': 'Assistente Pastita',
    'agent_description': 'Assistente virtual para atendimento ao cliente da Pastita',
    'agent_provider': 'kimi',
    'agent_model': 'kimi-coder',
    'agent_temperature': 0.7,
    'agent_max_tokens': 1000,
    'agent_system_prompt': """Você é o assistente virtual da Pastita, uma loja de massas artesanais.

Suas responsabilidades:
- Responder dúvidas sobre o cardápio e produtos
- Ajudar clientes a fazer pedidos
- Informar sobre horário de funcionamento e entregas
- Ser sempre educado, prestativo e gentil

Se não souber responder algo específico, direcione o cliente para falar com um atendente humano.""",
    'agent_base_url': 'https://api.kimi.com/coding/v1',
    'agent_timeout': 30,
    'agent_use_memory': True,
    'agent_memory_ttl': 3600,
}


# ============================================================================
# FUNÇÕES DE CRIAÇÃO
# ============================================================================

def create_agent(config: dict) -> Agent:
    """Cria ou retorna Agent IA existente."""
    name = config['agent_name']
    
    agent = Agent.objects.filter(name=name).first()
    if agent:
        print(f'✓ Agent "{name}" já existe (ID: {agent.id})')
        return agent
    
    agent = Agent.objects.create(
        name=name,
        description=config['agent_description'],
        provider=config['agent_provider'],
        model_name=config['agent_model'],
        temperature=config['agent_temperature'],
        max_tokens=config['agent_max_tokens'],
        system_prompt=config['agent_system_prompt'],
        base_url=config['agent_base_url'],
        api_key=config.get('agent_api_key', ''),
        timeout=config['agent_timeout'],
        status=Agent.AgentStatus.ACTIVE,
        use_memory=config['agent_use_memory'],
        memory_ttl=config['agent_memory_ttl'],
    )
    print(f'✓ Agent criado: {name} (ID: {agent.id})')
    return agent


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def parse_args():
    """Parse argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description='Script para criar/atualizar Agent IA (Kimi).'
    )
    
    # Agent
    parser.add_argument('--agent-name', default=DEFAULT_CONFIG['agent_name'])
    parser.add_argument('--agent-api-key', default='', help='API Key para o provedor de IA')
    parser.add_argument('--agent-model', default=DEFAULT_CONFIG['agent_model'])
    parser.add_argument('--agent-base-url', default=DEFAULT_CONFIG['agent_base_url'])
    parser.add_argument('--agent-temperature', type=float, default=DEFAULT_CONFIG['agent_temperature'])
    parser.add_argument('--agent-max-tokens', type=int, default=DEFAULT_CONFIG['agent_max_tokens'])
    parser.add_argument('--agent-timeout', type=int, default=DEFAULT_CONFIG['agent_timeout'])
    parser.add_argument('--agent-no-memory', action='store_true', help='Desabilitar memória do agente')
    parser.add_argument('--agent-memory-ttl', type=int, default=DEFAULT_CONFIG['agent_memory_ttl'])
    
    return parser.parse_args()


def main():
    """Função principal."""
    args = parse_args()
    
    # Mesclar argumentos com configuração padrão
    config = DEFAULT_CONFIG.copy()
    config.update({
        'agent_name': args.agent_name,
        'agent_api_key': args.agent_api_key,
        'agent_model': args.agent_model,
        'agent_base_url': args.agent_base_url,
        'agent_temperature': args.agent_temperature,
        'agent_max_tokens': args.agent_max_tokens,
        'agent_timeout': args.agent_timeout,
        'agent_use_memory': not args.agent_no_memory,
        'agent_memory_ttl': args.agent_memory_ttl,
    })
    
    print('=' * 60)
    print('🍝 PASTITA - SETUP DO AGENTE IA')
    print('=' * 60)
    print()
    
    try:
        with transaction.atomic():
            print('[1/1] Criando Agent IA...')
            agent = create_agent(config)
            print()
            
    except Exception as e:
        print(f'\n❌ ERRO: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Resumo final
    print('=' * 60)
    print('✅ SETUP CONCLUÍDO COM SUCESSO!')
    print('=' * 60)
    print()
    print('🤖 AGENT IA:')
    print(f'   Status: Ativo')
    print(f'   Provedor: {config["agent_provider"].upper()}')
    print(f'   Modelo: {config["agent_model"]}')
    print(f'   Base URL: {config["agent_base_url"]}')
    print()
    
    print('=' * 60)
    print('🚀 Próximos passos:')
    print('   1. Defina a KIMI_API_KEY no .env ou passe --agent-api-key')
    print('   2. Verifique o agente no Admin Django')
    print('=' * 60)


if __name__ == '__main__':
    main()
