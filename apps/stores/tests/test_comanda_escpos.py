"""Bytes ESC/POS da comanda montada no servidor + `escpos_b64` no payload.

O agente 0.6.0 despeja `escpos_b64` direto na impressora; o agente velho
ignora a chave e segue montando como sempre (contrato §3).
"""
import base64
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder, StoreOrderItem
from apps.stores.services import comanda_linhas as cl
from apps.stores.services.comanda_escpos import bytes_da_comanda
from apps.stores.services.print_service import build_order_print_payload

ESC, GS = 0x1B, 0x1D


def _linhas():
    return cl.linhas_da_comanda(cl.pedido_de_exemplo(), cl.layout_padrao())


class TestBytes:
    def test_comeca_com_esc_arroba_e_codepage_850(self):
        dados = bytes_da_comanda(_linhas(), 48)
        assert dados[:2] == bytes([ESC, 0x40])
        assert bytes([ESC, 0x74, 0x02]) in dados[:8]

    def test_texto_vai_em_cp850(self):
        linhas = [{'texto': 'Cê Saladas · 3º pedido', 'alinhar': 'centro', 'negrito': True,
                   'altura_dupla': False, 'largura_dupla': False, 'invertido': False, 'tipo': 'texto'}]
        dados = bytes_da_comanda(linhas, 48)
        assert 'Cê Saladas · 3º pedido'.encode('cp850') in dados
        assert bytes([ESC, 0x61, 0x01]) in dados  # centro
        assert bytes([ESC, 0x45, 0x01]) in dados  # negrito

    def test_invertido_altura_dupla_barras_e_corte(self):
        dados = bytes_da_comanda(_linhas(), 48)
        assert bytes([GS, 0x42, 0x01]) in dados       # invertido (COBRAR)
        assert bytes([GS, 0x21, 0x11]) in dados       # nº curto grande
        assert bytes([GS, 0x6B, 0x49]) in dados       # CODE128
        assert dados.endswith(bytes([GS, 0x56, 66, 0]))

    def test_estilos_desligados_depois_da_linha(self):
        dados = bytes_da_comanda(_linhas(), 48)
        assert bytes([GS, 0x42, 0x00]) in dados
        assert bytes([GS, 0x21, 0x00]) in dados


@pytest.mark.django_db
class TestPayload:
    @pytest.fixture
    def pedido(self):
        dono = get_user_model().objects.create_user(username='dono-esc', email='dono-esc@t.local', password='x')
        loja = Store.objects.create(owner=dono, name='Loja Esc', slug='loja-esc', status='active')
        pedido = StoreOrder.objects.create(
            store=loja, order_number='CE-2610225590', customer_name='Ana', customer_phone='63999990000',
            subtotal=Decimal('42.90'), total=Decimal('42.90'), payment_method='pix', payment_status='paid',
        )
        StoreOrderItem.objects.create(order=pedido, product_name='Salada Caesar', quantity=1,
                                      unit_price=Decimal('42.90'), subtotal=Decimal('42.90'))
        return pedido

    def test_kitchen_ticket_leva_escpos_b64(self, pedido):
        payload = build_order_print_payload(pedido)
        dados = base64.b64decode(payload['escpos_b64'])
        assert dados.startswith(bytes([ESC, 0x40]))
        assert 'Salada Caesar'.encode('cp850') in dados
        # O resto do payload continua lá para o agente velho.
        assert payload['items'][0]['name'] == 'Salada Caesar'

    def test_prep_ticket_tambem(self, pedido):
        assert build_order_print_payload(pedido, template='prep_ticket').get('escpos_b64')

    def test_via_de_montagem_nao_mostra_preco(self, pedido):
        # Dono 26/10: "no layout de montagem, não é para aparecer os preços".
        dados = base64.b64decode(build_order_print_payload(pedido, template='prep_ticket')['escpos_b64'])
        assert b'R$' not in dados
        assert b'TOTAL' not in dados
        assert 'Salada Caesar'.encode('cp850') in dados

    def test_recibo_do_cliente_nao_leva(self, pedido):
        assert 'escpos_b64' not in build_order_print_payload(pedido, template='customer_receipt')

    def test_duas_vias_repetem_os_bytes(self, pedido):
        uma = base64.b64decode(build_order_print_payload(pedido)['escpos_b64'])
        loja = pedido.store
        loja.metadata = {**(loja.metadata or {}), 'comanda': {**cl.layout_padrao(), 'vias': 2}}
        loja.save(update_fields=['metadata'])
        pedido.refresh_from_db()
        duas = base64.b64decode(build_order_print_payload(pedido)['escpos_b64'])
        # O rodapé tem a hora: compara o tamanho, não os bytes.
        assert len(duas) == 2 * len(uma)
        assert duas.count(bytes([ESC, 0x40])) == 2

    def test_layout_quebrado_na_loja_nao_derruba_a_comanda(self, pedido):
        loja = pedido.store
        loja.metadata = {'comanda': {'colunas': 999}}
        loja.save(update_fields=['metadata'])
        pedido.refresh_from_db()
        payload = build_order_print_payload(pedido)
        # Cai no padrão em vez de ficar sem comanda.
        assert payload.get('escpos_b64')
