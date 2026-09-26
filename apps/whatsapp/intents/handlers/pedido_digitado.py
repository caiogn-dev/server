"""A porta única do pedido digitado em texto livre.

Antes, o regex `create_order` ("vou querer…") mandava a frase para um extrator
que escolhia o item sozinho — em 25/09 ele pôs 1× Cebola roxa no carrinho de
quem escreveu "sem cebola roxa". Agora quem entende a frase é a triagem; aqui
só se age sobre o que ela leu:

- um vencedor claro por trecho → segue o pedido;
- empate → "qual destes?" com botões `qual_<id>`, sem chutar;
- "sem …" / "acrescenta …" → observação do pedido.
"""
import logging
from typing import Optional

from apps.whatsapp.formatacao import moeda

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)

PREFIXO_ESCOLHA = 'qual_'


class PedidoDigitadoHandler(IntentHandler):

    def propor(self, texto: str) -> Optional[HandlerResult]:
        """None quando a frase não pede produto — o roteamento normal segue."""
        from apps.automation.services.triagem import Intencao, triar
        from apps.stores.models import StoreCombo
        from apps.stores.services.leitura_do_pedido import ler_pedido

        if not self.store or triar(texto, store=self.store).intencao is not Intencao.ITEM:
            return None
        leitura = ler_pedido(self.store, texto)
        lidos = [o for o, _ in leitura.itens] + [o for grupo, _ in leitura.duvidas for o in grupo]
        if not lidos:
            return None
        if any(isinstance(o, StoreCombo) for o in lidos):
            # Combo tem montagem própria (sabores); o card de combo a inicia.
            from .catalog import ProductMentionHandler
            return ProductMentionHandler(self.account, self.conversation, self.company_profile).handle(
                {'original_message': texto},
            )
        return self._seguir({
            'itens': [{'product_id': str(o.id), 'quantity': q} for o, q in leitura.itens],
            'duvidas': [{'opcoes': [str(o.id) for o in grupo], 'quantidade': q}
                        for grupo, q in leitura.duvidas],
            'notas': '; '.join(leitura.notas),
        })

    def escolher(self, product_id: str) -> HandlerResult:
        """Clique em `qual_<id>`: resolve a primeira dúvida e segue."""
        sessao = self._get_session_manager()
        estado = sessao.pedido_digitado()
        if not estado.get('duvidas'):
            from .catalog import MenuRequestHandler
            return MenuRequestHandler(self.account, self.conversation, self.company_profile).handle({})
        duvida = estado['duvidas'].pop(0)
        estado['itens'].append({'product_id': str(product_id), 'quantity': duvida['quantidade']})
        return self._seguir(estado)

    def _seguir(self, estado: dict) -> HandlerResult:
        sessao = self._get_session_manager()
        if estado['duvidas']:
            sessao.guardar_pedido_digitado(estado)
            return self._perguntar_qual(estado['duvidas'][0]['opcoes'])
        sessao.descartar_pedido_digitado()
        if estado['notas']:
            sessao.save_customer_notes(estado['notas'])
        return self._ask_delivery_method(estado['itens'])

    def _perguntar_qual(self, opcoes: list) -> HandlerResult:
        from apps.stores.models import StoreProduct

        produtos = [p for p in StoreProduct.objects.filter(id__in=opcoes, store=self.store)]
        produtos.sort(key=lambda p: opcoes.index(str(p.id)))
        linhas = '\n'.join(f'• {p.name} — {moeda(p.preco_vigente())}' for p in produtos)
        return HandlerResult.buttons(
            body=f'Achei mais de um com esse nome 👇\n\n{linhas}\n\nQual destes você quer?',
            buttons=[{'id': f'{PREFIXO_ESCOLHA}{p.id}', 'title': p.name[:20]} for p in produtos],
        )
