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


def test_estornado_nao_vira_falha():
    """Dinheiro que ENTROU e voltou não é o mesmo caso de nunca ter sido
    autorizado. Cair no 'failed' fez o handler gravar como se a cobrança
    nunca tivesse tido sucesso."""
    ok, status, eid, _ = po.interpret(200, corpo('refunded', order_status='paid'))
    assert (ok, status) == (False, 'refunded')


def test_chargeback_tambem_vira_estornado():
    """Chargeback é dinheiro reversado, não um pagamento que falhou ao autorizar."""
    ok, status, eid, _ = po.interpret(200, corpo('chargedback', order_status='paid'))
    assert (ok, status) == (False, 'refunded')


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



def test_verifique_os_dados_do_cartao_tem_saida_propria():
    """A recusa que o adquirente REALMENTE devolve quando o cartao nao existe.

    Medido em 22/09 contra a API de producao, com o cartao de teste do
    simulador batendo na adquirente de verdade:

        acquirer_return_code : 1011
        acquirer_message     : 'Verifique os dados do cartao'

    Era a unica recusa ja observada em producao (7 de 7 orders) e caia no
    texto generico, que manda o cliente "usar outro cartao" quando o problema
    provavel e um digito errado no que ele acabou de preencher. Trocar de
    cartao por causa de um typo e conselho errado.
    """
    msg = po.mensagem_de_recusa('Verifique os dados do cartão')
    assert msg != po.RECUSA_GENERICA
    assert 'confira' in msg.lower() or 'verifique' in msg.lower()


#: Forma natural (acentuada) com que o adquirente manda cada motivo.
#: A chave do dicionario e a versao ja normalizada; se o teste usasse a
#: chave, ele nao passaria pela transliteracao e nao provaria nada.
MOTIVOS_COMO_O_ADQUIRENTE_MANDA = {
    'saldo insuficiente': 'Saldo insuficiente',
    'cartao expirado': 'Cartão expirado',
    'cartao invalido': 'Cartão inválido',
    'senha invalida': 'Senha inválida',
    'transacao nao permitida': 'Transação não permitida',
    'estabelecimento invalido': 'Estabelecimento inválido',
    'cartao bloqueado': 'Cartão bloqueado',
    'verifique os dados do cartao': 'Verifique os dados do cartão',
}


def test_toda_chave_do_dicionario_e_alcancavel_a_partir_do_texto_acentuado():
    """Se alguem remover a transliteracao, TODA entrada acentuada cai no
    generico e este teste quebra na hora — que e o ponto dele."""
    assert set(MOTIVOS_COMO_O_ADQUIRENTE_MANDA) == set(po.MENSAGENS_DE_RECUSA), (
        'Entrada nova em MENSAGENS_DE_RECUSA sem forma acentuada correspondente.'
    )
    for chave, acentuado in MOTIVOS_COMO_O_ADQUIRENTE_MANDA.items():
        assert po.mensagem_de_recusa(acentuado) == po.MENSAGENS_DE_RECUSA[chave]
