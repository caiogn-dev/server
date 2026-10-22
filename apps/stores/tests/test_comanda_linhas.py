"""Comanda montada no servidor (22/10): as linhas que viram papel E prévia.

Contrato em docs/comanda-no-servidor.md. Estas linhas são a fonte única: o
painel desenha a prévia a partir delas e `comanda_escpos` as converte em
bytes. Teste puro, sem banco: o payload é o mesmo dict do print_service.
"""
import copy

from apps.stores.services import comanda_linhas as cl


def _payload(**sobre):
    base = {
        'template': 'kitchen_ticket',
        'generated_at': '2026-10-22T15:04:05+00:00',
        'store': {'name': 'Cê Saladas', 'phone': '(63) 3025-0000', 'logo_escpos': None},
        'order': {
            'order_number': 'CE-2610225590',
            'created_at': '2026-10-22T15:00:00+00:00',
            'scheduled_for': '',
            'delivery_method': 'delivery',
            'payment_method': 'card_on_delivery',
            'payment_status': 'pending',
            'source': 'whatsapp',
            'coupon_code': 'BEMVINDO10',
            'customer_notes': 'Tocar o interfone',
            'internal_notes': '',
            'delivery_notes': '',
            'change_for': None,
            'change_due': None,
        },
        'customer': {'name': 'Ana Paula', 'phone': '63999990000', 'pedidos': 3},
        'address_lines': ['Rua 10, nº 5', 'Apto 2 - Plano Diretor Sul', 'Palmas / TO'],
        'address_warning': [],
        'items': [
            {
                'type': 'item', 'qty': 1, 'name': 'Salada Caesar', 'unit_price': '42.90',
                'subtotal': '42.90', 'details': ['Frango', 'Sem cebola'], 'ingredients': [],
                'prep': ['>> 1 SALADA'], 'notes': 'caprichar no molho',
            },
        ],
        'totals': {
            'subtotal': '42.90', 'discount': '4.29', 'delivery_fee': '8.00',
            'voucher_fee': '0.00', 'total': '46.61',
            'descontos': [{'tipo': 'cupom', 'rotulo': 'Cupom BEMVINDO10', 'valor': '4.29', 'codigo': 'BEMVINDO10'}],
        },
    }
    for chave, valor in sobre.items():
        if isinstance(valor, dict) and isinstance(base.get(chave), dict):
            base[chave] = {**base[chave], **valor}
        else:
            base[chave] = valor
    return base


def _textos(linhas):
    return [l['texto'] for l in linhas]


def _junto(linhas):
    return '\n'.join(_textos(linhas))


def _layout(**sobre):
    layout = cl.layout_padrao()
    layout.update(sobre)
    return cl.validar_layout(layout)


class TestLayout:
    def test_padrao_tem_os_onze_blocos_na_ordem(self):
        ids = [b['id'] for b in cl.layout_padrao()['blocos']]
        assert ids == ['cabecalho', 'numero', 'pagamento', 'cliente', 'endereco', 'avisos',
                       'itens', 'totais', 'observacao', 'mensagem', 'codigo_barras']
        mensagem = [b for b in cl.layout_padrao()['blocos'] if b['id'] == 'mensagem'][0]
        assert mensagem['ligado'] is False

    def test_bloco_desconhecido_some_e_faltante_entra_desligado_no_fim(self):
        layout = cl.validar_layout({'blocos': [{'id': 'itens', 'ligado': True}, {'id': 'xpto', 'ligado': True}]})
        ids = [b['id'] for b in layout['blocos']]
        assert ids[0] == 'itens'
        assert 'xpto' not in ids
        assert len(ids) == 11
        assert all(not b['ligado'] for b in layout['blocos'][1:])

    def test_valores_invalidos_sao_recusados(self):
        import pytest
        for ruim in ({'colunas': 40}, {'vias': 3}, {'separador': 'estrela'}, {'mensagem': 'x' * 201}):
            with pytest.raises(cl.LayoutInvalido):
                cl.validar_layout({**cl.layout_padrao(), **ruim})


class TestBlocos:
    def test_tudo_cabe_em_48_colunas(self):
        for l in cl.linhas_da_comanda(_payload(), _layout()):
            largura = 24 if l['largura_dupla'] else 48
            assert len(l['texto']) <= largura, l

    def test_tudo_cabe_em_32_colunas(self):
        p = _payload(order={'payment_method': 'voucher_link', 'delivery_method': 'digital'})
        for l in cl.linhas_da_comanda(p, _layout(colunas=32)):
            largura = 16 if l['largura_dupla'] else 32
            assert len(l['texto']) <= largura, l

    def test_numero_curto_grande_com_tipo_na_mesma_linha(self):
        linhas = cl.linhas_da_comanda(_payload(), _layout())
        grande = [l for l in linhas if '#5590' in l['texto']][0]
        assert 'ENTREGA' in grande['texto']
        assert grande['altura_dupla'] and grande['largura_dupla']
        assert any('CE-2610225590' in t for t in _textos(linhas))

    def test_tipo_retirada_e_link(self):
        assert 'RETIRADA' in _junto(cl.linhas_da_comanda(_payload(order={'delivery_method': 'pickup'}), _layout()))
        assert 'PAGTO POR LINK' in _junto(cl.linhas_da_comanda(_payload(order={'delivery_method': 'digital'}), _layout()))

    def test_nao_pago_sai_cobrar_invertido_com_a_forma(self):
        linhas = cl.linhas_da_comanda(_payload(), _layout())
        cobrar = [l for l in linhas if l['texto'].strip().startswith('COBRAR')][0]
        assert cobrar['invertido']
        assert 'R$ 46,61' in cobrar['texto']
        assert 'levar maquininha' in _junto(linhas)

    def test_pago_sai_pago_com_forma_e_sem_cobrar(self):
        linhas = cl.linhas_da_comanda(_payload(order={'payment_status': 'paid', 'payment_method': 'pix'}), _layout())
        assert 'PAGO · PIX' in _junto(linhas)
        assert 'COBRAR' not in _junto(linhas)

    def test_troco(self):
        p = _payload(order={'payment_method': 'cash', 'change_for': '100.00', 'change_due': '53.39'})
        texto = _junto(cl.linhas_da_comanda(p, _layout()))
        assert 'R$ 100,00' in texto and 'R$ 53,39' in texto
        p = _payload(order={'payment_method': 'cash', 'change_for': '0.00', 'change_due': '0.00'})
        assert 'SEM TROCO' in _junto(cl.linhas_da_comanda(p, _layout()))

    def test_cupom_sai_pelo_codigo(self):
        texto = _junto(cl.linhas_da_comanda(_payload(), _layout()))
        assert 'Cupom BEMVINDO10' in texto
        assert '- R$ 4,29' in texto

    def test_cupom_sem_lista_do_servidor_ainda_mostra_o_codigo(self):
        p = _payload(totals={'descontos': []})
        assert 'Cupom BEMVINDO10' in _junto(cl.linhas_da_comanda(p, _layout()))

    def test_terceiro_pedido_na_linha_do_nome(self):
        linhas = cl.linhas_da_comanda(_payload(), _layout())
        nome = [l for l in linhas if 'ANA PAULA' in l['texto']][0]
        assert '3º pedido' in nome['texto']

    def test_primeiro_pedido_sai_invertido(self):
        linhas = cl.linhas_da_comanda(_payload(customer={'pedidos': 1}), _layout())
        novo = [l for l in linhas if '1º PEDIDO' in l['texto']][0]
        assert novo['invertido'] and 'CLIENTE NOVO' in novo['texto']

    def test_bairro_em_altura_dupla(self):
        linhas = cl.linhas_da_comanda(_payload(), _layout())
        bairro = [l for l in linhas if 'Plano Diretor Sul' in l['texto']][0]
        assert bairro['altura_dupla']

    def test_item_com_preco_opcao_e_remocao_invertida(self):
        linhas = cl.linhas_da_comanda(_payload(), _layout())
        item = [l for l in linhas if 'Salada Caesar' in l['texto']][0]
        assert item['texto'].startswith('1 x Salada Caesar') and item['texto'].endswith('R$ 42,90')
        assert any(l['texto'].startswith('    Frango') for l in linhas)
        sem = [l for l in linhas if 'Sem cebola' in l['texto']][0]
        assert sem['invertido']
        assert 'CAPRICHAR NO MOLHO' in _junto(linhas)

    def test_sem_precos_nos_itens(self):
        linhas = cl.linhas_da_comanda(_payload(), _layout(precos_nos_itens=False))
        item = [l for l in linhas if 'Salada Caesar' in l['texto']][0]
        assert 'R$' not in item['texto']

    def test_preparo_so_na_prep_ticket(self):
        assert '>> 1 SALADA' not in _junto(cl.linhas_da_comanda(_payload(), _layout()))
        prep = cl.linhas_da_comanda(_payload(template='prep_ticket'), _layout())
        assert '>> 1 SALADA' in _junto(prep)

    def test_avisos_endereco_atencao_e_agendamento(self):
        p = _payload(
            address_warning=['!! CONFERIR ENDERECO ANTES DE SAIR !!', 'Cliente escreveu: Rua A', 'Pin do mapa cai em: Rua B'],
            order={'internal_notes': 'Cliente VIP', 'scheduled_for': '2026-10-23 12:00'},
        )
        texto = _junto(cl.linhas_da_comanda(p, _layout()))
        for trecho in ('CONFERIR ENDERECO', 'Pin do mapa cai em: Rua B', 'ATENCAO DA LOJA', 'Cliente VIP', 'AGENDADO 23/10 12:00'):
            assert trecho in texto

    def test_acrescimo_de_vale_e_observacao(self):
        p = _payload(totals={'voucher_fee': '3.50'})
        texto = _junto(cl.linhas_da_comanda(p, _layout()))
        assert 'Acrescimo vale' in texto and 'Tocar o interfone' in texto

    def test_codigo_de_barras_e_rodape(self):
        linhas = cl.linhas_da_comanda(_payload(), _layout())
        barras = [l for l in linhas if l['tipo'] == 'codigo_barras'][0]
        assert barras['texto'] == 'CE-2610225590'
        assert any(l['texto'].strip().startswith('Impresso ') and 'Cê Saladas' in l['texto'] for l in linhas)
        assert linhas[-1]['tipo'] == 'corte'

    def test_separador_tracejado_entre_blocos(self):
        linhas = cl.linhas_da_comanda(_payload(), _layout())
        seps = [l for l in linhas if l['tipo'] == 'separador']
        assert seps and seps[0]['texto'].startswith('- - ')
        linhas = cl.linhas_da_comanda(_payload(), _layout(separador='espaco'))
        assert not [l for l in linhas if l['tipo'] == 'separador']

    def test_bloco_desligado_nao_sai(self):
        layout = cl.layout_padrao()
        for b in layout['blocos']:
            if b['id'] in ('pagamento', 'codigo_barras'):
                b['ligado'] = False
        linhas = cl.linhas_da_comanda(_payload(), cl.validar_layout(layout))
        assert 'COBRAR' not in _junto(linhas)
        assert not [l for l in linhas if l['tipo'] == 'codigo_barras']

    def test_ordem_dos_blocos_manda_no_papel(self):
        layout = cl.layout_padrao()
        layout['blocos'] = sorted(layout['blocos'], key=lambda b: b['id'] != 'itens')  # itens primeiro
        textos = _textos(cl.linhas_da_comanda(_payload(), cl.validar_layout(layout)))
        pos_item = next(i for i, t in enumerate(textos) if 'Salada Caesar' in t)
        pos_numero = next(i for i, t in enumerate(textos) if '#5590' in t)
        assert pos_item < pos_numero

    def test_mensagem_livre(self):
        layout = cl.layout_padrao()
        for b in layout['blocos']:
            if b['id'] == 'mensagem':
                b['ligado'] = True
        layout['mensagem'] = 'Obrigado pela preferência!'
        assert 'Obrigado pela preferência!' in _junto(cl.linhas_da_comanda(_payload(), cl.validar_layout(layout)))

    def test_itens_grandes(self):
        linhas = cl.linhas_da_comanda(_payload(), _layout(itens_grandes=True))
        assert [l for l in linhas if 'Salada Caesar' in l['texto']][0]['altura_dupla']

    def test_nao_altera_o_payload(self):
        p = _payload()
        antes = copy.deepcopy(p)
        cl.linhas_da_comanda(p, _layout())
        assert p == antes

    def test_pedido_de_exemplo_monta(self):
        linhas = cl.linhas_da_comanda(cl.pedido_de_exemplo(), cl.layout_padrao())
        assert any('x ' in l['texto'] for l in linhas)
