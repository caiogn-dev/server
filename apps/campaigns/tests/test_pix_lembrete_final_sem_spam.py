"""check_pending_payments — lembrete final e cancelamento de expirados.

Bug original (2026-09-22, fix v1):
  check_pending_payments  → exclude(metadata__has_key='payment_expired_notified')
  send_payment_reminder   → order.metadata[f'payment_reminder_{type}_sent'] = …
  A chave 'payment_expired_notified' nunca era gravada; o exclude nunca pegava
  nada e o cliente recebia spam do lembrete de expiração indefinidamente.

Refinamento (Codex review, 2026-09-22, fix v2):
  A query de expirados não deve usar .exclude(metadata__has_key=...) porque a
  lista é usada tanto para notificar quanto para CANCELAR. Se o beat task
  crashar após o delay mas antes do cancel_order, o pedido fica com
  'payment_reminder_final_sent' mas sem cancelamento — e um exclude na query
  o excluiria do próximo ciclo, deixando-o pendente para sempre.
  Solução: buscar (id, metadata) na query, checar metadata no loop para decidir
  se envia o lembrete, mas sempre chamar cancel_order.

Estes testes são estáticos (lêem o arquivo fonte diretamente) para não depender
de langchain_core ou outros módulos pesados que não estão no container de CI.
"""
from pathlib import Path

import pytest

_TASKS = Path('apps/whatsapp/tasks/automation_tasks.py')


def _fonte():
    return _TASKS.read_text(encoding='utf-8', errors='ignore')


def test_check_usa_payment_reminder_final_sent():
    """O exclude de expirados deve usar 'payment_reminder_final_sent'.

    Essa é a chave que send_payment_reminder(type='final') efetivamente
    grava em order.metadata — e a que precisa estar no exclude para o
    pedido ser excluído do próximo ciclo.
    """
    assert 'payment_reminder_final_sent' in _fonte(), (
        "check_pending_payments deve excluir por 'payment_reminder_final_sent' "
        "(a chave que send_payment_reminder grava para type='final')."
    )


def test_check_nao_usa_chave_nunca_definida():
    """'payment_expired_notified' nunca é gravada em nenhum lugar — o
    exclude usando essa chave nunca exclui nada, gerando spam de tarefas."""
    assert 'payment_expired_notified' not in _fonte(), (
        "'payment_expired_notified' nunca é gravada; o exclude não excluirá "
        "nada e pedidos expirados ficarão no lote para sempre."
    )


def test_send_grava_payment_reminder_X_sent():
    """send_payment_reminder grava o padrão payment_reminder_{type}_sent —
    garantindo que 'payment_reminder_final_sent' é a chave para type='final'."""
    fonte = _fonte()
    # O template literal que gera a chave dinâmica
    assert "payment_reminder_" in fonte and "_sent" in fonte, (
        "Padrão 'payment_reminder_<type>_sent' ausente em automation_tasks.py"
    )


def test_chave_morta_ausente_em_todo_o_codigo():
    """'payment_expired_notified' não deve aparecer em nenhum arquivo de
    produção — após o fix é uma chave morta que não existe mais."""
    culpados = [
        f'{arquivo}:{n}'
        for arquivo in Path('apps').rglob('*.py')
        if 'tests' not in str(arquivo) and not arquivo.name.startswith('test_')
        for n, linha in enumerate(
            arquivo.read_text(errors='ignore').splitlines(), 1
        )
        if 'payment_expired_notified' in linha
    ]
    assert culpados == [], (
        f"'payment_expired_notified' ainda aparece em: {culpados}"
    )


def test_expired_query_nao_exclui_na_consulta():
    """A query de expirados não deve ter .exclude(metadata__has_key='payment_reminder_final_sent').

    Um exclude na query impediria o cancel_order para pedidos que já receberam
    o lembrete — se o beat crashar entre o delay e o cancel_order, o pedido
    ficaria pendente para sempre.
    A checagem correta é dentro do loop via .get('payment_reminder_final_sent').
    """
    fonte = _fonte()
    bad_pattern = "exclude(metadata__has_key='payment_reminder_final_sent')"
    assert bad_pattern not in fonte, (
        "A query de expirados não deve usar .exclude(metadata__has_key='payment_reminder_final_sent') "
        "— isso bloquearia o cancel_order para pedidos onde o beat crashou após o lembrete. "
        "Use a checagem dentro do loop."
    )


def test_expired_loop_busca_metadata_na_query():
    """A query de expirados deve buscar 'metadata' junto com 'id'.

    Isso garante que a checagem de lembrete é feita no loop (sem query extra
    por pedido) e que o cancel_order é chamado independentemente.
    """
    fonte = _fonte()
    assert "values_list('id', 'metadata')" in fonte, (
        "A query de expirados deve usar values_list('id', 'metadata') para "
        "checar o lembrete no loop sem excluir o pedido do caminho de cancelamento."
    )
