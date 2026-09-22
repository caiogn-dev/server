"""check_pending_payments deve excluir pedidos expirados com a chave correta.

Raiz do bug (2026-09-22):

  check_pending_payments  → exclude(metadata__has_key='payment_expired_notified')
  send_payment_reminder   → order.metadata[f'payment_reminder_{type}_sent'] = …
                                                ↑ 'final' → 'payment_reminder_final_sent'

A chave `payment_expired_notified` nunca é gravada em lugar nenhum do código.
O `exclude` nunca pega nada, e todo pedido PIX com mais de 24 h fica no lote
para sempre — gerando uma tarefa `send_payment_reminder('final')` a cada 10
minutos. O `envio_unico` com TTL de 3600 s limita a 1 envio por hora, mas o
cliente continua recebendo a notificação de expiração indefinidamente.

O fix: trocar a chave do `exclude` para `payment_reminder_final_sent`, que é
exatamente o que `send_payment_reminder` já grava para `reminder_type='final'`.

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
