"""Mensageiro: por onde toda mensagem automática de WhatsApp sai.

Fase 1 (19/09/2026): trava única e canal único que grava a mensagem na
conversa. Plano: docs/superpowers/plans/2026-09-19-mensageiro-fase1.md.
"""
from .trava import liberar, reservar  # noqa: F401
from .canal import EnvioFalhou, enviar_botoes, enviar_texto  # noqa: F401,E402

from . import janela  # noqa: E402,F401  — a regra das 24 h
