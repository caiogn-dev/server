"""Segunda camada de verificação da janela de 24h no envio de campanha.

PROBLEMA ANÁLOGO AO OPT-OUT DE 25→28/AGO:

O incidente de opt-out mostrou que uma segunda camada de verificação É
NECESSÁRIA no momento do envio — a lista pode ter sido montada antes do pedido
de saída e disparada depois.

A mesma lógica vale para a janela de 24h de campanhas do tipo
`somente_janela_aberta`:

  1. Campanha começa às 15:00 com 1.000 destinatários — janela verificada.
  2. Destinatário X tinha a janela aberta em 15:00 (última mensagem: 15:30
     de ontem → fecha às 15:30 de hoje).
  3. O lote de X só é processado em 15:45.
  4. A janela de X fechou às 15:30.
  5. A API da Meta retorna 131047. O envio é marcado como FAILED.

FAILED é errado: a janela fechou, não houve falha técnica. O correto é SKIPPED,
pelo mesmo motivo do opt-out — não é erro, é situação do destinatário.
Marcar como FAILED infla a taxa de erros da campanha, esconde falhas reais e
faz o dono da loja pensar que há problema técnico onde há só timing.

A correção é idêntica ao opt-out: verificar a janela em CADA LOTE — bulk
(uma consulta por lote, não uma por destinatário) — e pular os que saíram.
"""
import ast
import textwrap
import unittest
from pathlib import Path

_SERVICE = (
    Path(__file__).resolve()
    .parent  # tests/
    .parent  # campaigns/
    .parent  # apps/
    / 'campaigns'
    / 'services'
    / 'campaign_service.py'
)


def _source_do_batch() -> str:
    """Extrai o source textual do método process_campaign_batch."""
    source = _SERVICE.read_text()
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == 'process_campaign_batch':
                start = node.lineno - 1
                end = node.end_lineno
                return '\n'.join(lines[start:end])
    raise AssertionError("process_campaign_batch não encontrado em campaign_service.py")


class JanelaSegundaCamadaTests(unittest.TestCase):
    """Verifica ESTATICAMENTE que process_campaign_batch aplica a janela."""

    def setUp(self):
        self.src = _source_do_batch()

    def test_batch_importa_fechamentos_por_chave(self):
        """process_campaign_batch deve buscar timestamps de fechamento por lote.

        fechamentos_por_chave é preferível a chaves_com_janela_aberta: ainda é
        uma query bulk (O(1) por lote), mas timezone.now() é chamado fresquinho
        por destinatário — elimina a janela de race dentro do loop do lote.
        """
        self.assertIn(
            'fechamentos_por_chave',
            self.src,
            "process_campaign_batch precisa chamar fechamentos_por_chave "
            "para retestar a janela por lote com relógio fresco por destinatário.",
        )

    def test_batch_verifica_a_marca_somente_janela_aberta(self):
        """O recorte por janela só faz sentido em campanhas marcadas como tal."""
        self.assertTrue(
            'MARCA' in self.src or 'somente_janela_aberta' in self.src,
            "process_campaign_batch deve verificar se a campanha é do tipo "
            "somente_janela_aberta antes de aplicar o filtro de janela.",
        )

    def test_batch_usa_skipped_para_janela_fechada(self):
        """Janela fechada durante o envio → SKIPPED, não FAILED.

        Análogo ao opt-out: não é falha técnica, é situação do destinatário.
        Marcar como FAILED inflaria a taxa de erros da campanha.
        """
        self.assertIn(
            'fechamentos_por_chave',
            self.src,
            "A segunda camada de janela precisa existir antes de verificar "
            "o SKIPPED; este teste está RED enquanto ela não existir.",
        )
        # O source deve conter SKIPPED na mesma função (o opt-out já garante
        # isso — mas queremos ter certeza que o caminho de janela também usa).
        self.assertIn(
            'SKIPPED',
            self.src,
            "process_campaign_batch deve marcar como SKIPPED (não FAILED) "
            "destinatários cuja janela fechou entre o início da campanha e "
            "o processamento do lote.",
        )

    def test_janela_segunda_camada_usa_continue_nao_messages_failed(self):
        """Pular por janela fechada não deve incrementar messages_failed.

        O bloco que detecta janela fechada deve usar 'continue', de forma que
        o código não caia no except que incrementa messages_failed.
        """
        if 'fechamentos_por_chave' not in self.src:
            self.skipTest("Segunda camada ainda não implementada (RED nos testes acima)")

        # Localiza o bloco de janela e verifica 'continue' antes do 'try' de envio
        janela_pos = self.src.find('fechamentos_por_chave')
        try_pos = self.src.find('    try:', janela_pos)
        between = self.src[janela_pos:try_pos] if try_pos > janela_pos else self.src[janela_pos:]
        self.assertIn(
            'continue',
            between,
            "O bloco que detecta janela fechada deve usar 'continue' para "
            "pular o envio sem incrementar messages_failed.",
        )


if __name__ == '__main__':
    unittest.main()
