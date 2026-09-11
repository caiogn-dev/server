from apps.stores.services import pagarme_orders as po


def corpo(status_charge, *, acquirer_message='', order_status='paid', oid='or_1'):
    return {
        'id': oid,
        'status': order_status,
        'charges': [{
            'id': 'ch_1',
            'status': status_charge,
            'last_transaction': {
                'acquirer_message': acquirer_message,
                'gateway_response': {},
            },
        }],
    }


def test_pago_vira_aprovado():
    ok, status, eid, motivo = po.interpret(200, corpo('paid'))
    assert (ok, status, eid) == (True, 'approved', 'or_1')


def test_recusado_vira_falha():
    ok, status, eid, _ = po.interpret(200, corpo('failed', order_status='failed'))
    assert (ok, status) == (False, 'failed')


def test_motivo_vem_do_campo_aninhado_e_nao_do_message_de_fora():
    """O motivo real mora em charges[0].last_transaction.acquirer_message.
    Ler o `message` de fora foi o que fez o cliente ver texto genérico no MP."""
    body = corpo('failed', acquirer_message='Saldo insuficiente', order_status='failed')
    body['message'] = 'The following transactions failed'
    _, _, _, motivo = po.interpret(200, body)
    assert motivo == 'Saldo insuficiente'


def test_http_de_erro_vira_falha():
    ok, status, _, _ = po.interpret(422, {'message': 'invalid card_token'})
    assert (ok, status) == (False, 'failed')


def test_corpo_vazio_nao_explode():
    ok, status, eid, _ = po.interpret(500, None)
    assert (ok, status, eid) == (False, 'failed', None)


def test_saldo_insuficiente_fala_portugues_e_sugere_saida():
    msg = po.mensagem_de_recusa('Saldo insuficiente')
    assert 'saldo' in msg.lower()
    assert 'pix' in msg.lower()


def test_motivo_desconhecido_nao_vaza_texto_tecnico():
    msg = po.mensagem_de_recusa('ERR_ACQ_5591_XYZ')
    assert 'ERR_ACQ' not in msg
    assert msg == po.RECUSA_GENERICA


def test_motivo_COM_ACENTO_chega_na_mensagem_especifica():
    msg = po.mensagem_de_recusa('Cartão bloqueado')
    assert msg != po.RECUSA_GENERICA
    assert 'bloqueado' in msg.lower()


def test_toda_chave_do_dicionario_e_alcancavel():
    for chave in po.MENSAGENS_DE_RECUSA:
        assert po.mensagem_de_recusa(chave) is not po.RECUSA_GENERICA
