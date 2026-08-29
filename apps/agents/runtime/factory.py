"""factory — criação (e cache) do cliente LLM e do cliente Redis.

Fonte única do que antes era LangchainService._create_llm / _create_redis_client.
Mantém a MESMA lógica de resolução (provider → key/base_url → strip de sufixo).
`get_llm(agent)` cacheia o cliente por agente+config (antes era recriado toda mensagem).
"""
import logging

from django.conf import settings

from apps.core.exceptions import BaseAPIException
from ..models import Agent

logger = logging.getLogger(__name__)


def create_redis_client():
    import redis
    redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
    return redis.from_url(redis_url, decode_responses=True)


def create_llm(agent: Agent):
    """Cria a instância LLM do Langchain conforme o provider do agente."""
    provider = agent.provider

    # ── Resolve API key: agent DB > provider-specific env var ─────────────
    _ENV_API_KEY = {
        Agent.AgentProvider.KIMI:      'KIMI_API_KEY',
        Agent.AgentProvider.OPENAI:    'OPENAI_API_KEY',
        Agent.AgentProvider.ANTHROPIC: 'ANTHROPIC_API_KEY',
        Agent.AgentProvider.NVIDIA:    'NVIDIA_API_KEY',
        Agent.AgentProvider.OLLAMA:    None,
    }
    env_key_name = _ENV_API_KEY.get(provider)
    api_key = agent.api_key or (
        getattr(settings, env_key_name, '') if env_key_name else ''
    ) or 'ollama'  # Ollama não requer key real

    # ── Resolve base URL: agent DB > provider-specific env var > hardcoded ─
    _ENV_BASE_URL = {
        Agent.AgentProvider.KIMI:      ('KIMI_BASE_URL',      'https://api.moonshot.cn/v1'),
        Agent.AgentProvider.OPENAI:    ('OPENAI_BASE_URL',    'https://api.openai.com/v1'),
        Agent.AgentProvider.ANTHROPIC: ('ANTHROPIC_BASE_URL', 'https://api.anthropic.com'),
        Agent.AgentProvider.NVIDIA:    ('NVIDIA_API_BASE_URL', 'https://integrate.api.nvidia.com/v1'),
        Agent.AgentProvider.OLLAMA:    ('OLLAMA_BASE_URL',    'http://localhost:11434/v1'),
    }
    env_url_name, default_url = _ENV_BASE_URL.get(provider, (None, ''))
    base_url = agent.base_url or (
        getattr(settings, env_url_name, '') if env_url_name else ''
    ) or default_url

    # Strip trailing endpoint paths que admins às vezes incluem por engano.
    for _suffix in ('/chat/completions', '/completions', '/v1/chat/completions'):
        if base_url.rstrip('/').endswith(_suffix):
            base_url = base_url.rstrip('/')[:-(len(_suffix))].rstrip('/')
            logger.warning('[LLM] base_url continha sufixo de endpoint — corrigido p/: %s', base_url)
            break

    if not api_key and provider != Agent.AgentProvider.OLLAMA:
        raise BaseAPIException(
            f"API Key não configurada para o agente (provider={provider}). "
            "Configure no Django Admin ou via variável de ambiente."
        )

    logger.debug('[LLM] Criando %s | model=%s | base_url=%s | key_set=%s',
                 provider, agent.model_name, base_url, bool(api_key))

    if provider == Agent.AgentProvider.KIMI:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=agent.model_name, temperature=agent.temperature,
            max_tokens=agent.max_tokens, timeout=agent.timeout,
            api_key=api_key, base_url=base_url,
            default_headers={
                'Content-Type': 'application/json; charset=utf-8',
                'Accept': 'application/json',
            },
        )
    elif provider == Agent.AgentProvider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=agent.model_name, temperature=agent.temperature,
            max_tokens=agent.max_tokens, timeout=agent.timeout,
            api_key=api_key, anthropic_api_url=base_url,
        )
    elif provider == Agent.AgentProvider.OPENAI:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=agent.model_name, temperature=agent.temperature,
            max_tokens=agent.max_tokens, timeout=agent.timeout,
            api_key=api_key, base_url=base_url or None,
        )
    elif provider == Agent.AgentProvider.OLLAMA:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=agent.model_name, temperature=agent.temperature,
            max_tokens=agent.max_tokens, timeout=agent.timeout,
            api_key=api_key, base_url=base_url,
        )
    elif provider == Agent.AgentProvider.NVIDIA:
        from langchain_openai import ChatOpenAI
        # `modelo_vivo` filtra modelo aposentado venha ele do agente ou do env.
        # O env de produção mora assado na imagem e continuou apontando para o
        # llama-3.1-70b depois do 410 dele — obedecê-lo manteria a falha viva.
        from .modelos import modelo_vivo
        model_name = modelo_vivo(
            agent.model_name or getattr(settings, 'NVIDIA_MODEL_NAME', '')
        )
        return ChatOpenAI(
            model=model_name, temperature=agent.temperature,
            max_tokens=agent.max_tokens, timeout=agent.timeout,
            api_key=api_key, base_url=base_url,
        )
    else:
        raise BaseAPIException(f"Provedor não suportado: {provider}")


# Cache de cliente LLM por agente+config (antes recriado a cada mensagem).
_LLM_CACHE = {}


def get_llm(agent: Agent):
    """Retorna o cliente LLM cacheado; recria se a config do agente mudou."""
    key = (
        str(agent.id), agent.provider, agent.model_name, agent.base_url,
        bool(agent.api_key), agent.temperature, agent.max_tokens, agent.timeout,
    )
    cached = _LLM_CACHE.get(str(agent.id))
    if cached and cached[0] == key:
        return cached[1]
    llm = create_llm(agent)
    _LLM_CACHE[str(agent.id)] = (key, llm)
    return llm
