"""Importar o cardápio de uma planilha — a hora da implantação em forma de código.

Medido na estratégia: a implantação custa **7,9 h por cliente**, e a maior
fatia é digitar produto por produto no formulário. Com 92 min/mês de suporte
por loja, o teto de um dev solo fica em ~35 clientes — e o teto é o que impede
vender volume, não o preço.

🚨 O importador "foto/PDF → produtos" da estratégia depende de LLM, e a chave
da NVIDIA está devolvendo 403 na inferência (medido em 22/09). Construir em
cima de um modelo morto entregaria uma tela que não funciona. Planilha é
determinístico: funciona hoje, e resolve a mesma hora.

As decisões que os testes fixam:

- **Preço em português.** "12,90" é como o dono escreve. Recusar isso faria o
  importador devolver o trabalho que ele veio tirar.
- **Uma linha ruim não derruba o arquivo.** Um cardápio de 80 itens com 2
  linhas tortas tem que importar 78 e dizer quais 2 falharam — abortar tudo
  obriga a recomeçar do zero.
- **Reimportar não duplica.** O dono vai corrigir a planilha e subir de novo;
  se isso duplicar, ele termina com 160 produtos.
- **Categoria nasce do nome.** Exigir que ele cadastre categorias antes seria
  mandar fazer à mão justamente o que ele veio automatizar.
"""
from decimal import Decimal

import pytest

from apps.stores.services import importador_de_cardapio as imp


class TestLeituraDaPlanilha:
    def test_preco_em_portugues_e_aceito(self):
        assert imp.ler_preco('12,90') == Decimal('12.90')
        assert imp.ler_preco('R$ 1.234,50') == Decimal('1234.50')
        assert imp.ler_preco('  49,99  ') == Decimal('49.99')

    def test_preco_em_formato_de_maquina_tambem(self):
        """Planilha exportada de sistema vem com ponto decimal."""
        assert imp.ler_preco('12.90') == Decimal('12.90')
        assert imp.ler_preco(49) == Decimal('49')

    def test_preco_impossivel_e_recusado_sem_inventar_valor(self):
        # Virar 0 seria pior que falhar: o produto entraria de graça no cardápio.
        for ruim in ('', None, 'grátis', 'a combinar', '-5'):
            with pytest.raises(imp.LinhaInvalida):
                imp.ler_preco(ruim)

    def test_cabecalho_aceita_as_variacoes_que_o_dono_escreve(self):
        """'Produto', 'Nome', 'NOME DO PRODUTO' são a mesma coluna."""
        for escrito in ('nome', 'Nome', 'PRODUTO', 'nome do produto', ' Produto '):
            assert imp.coluna_canonica(escrito) == 'nome'
        for escrito in ('preço', 'PRECO', 'valor', 'Preço (R$)'):
            assert imp.coluna_canonica(escrito) == 'preco'
        for escrito in ('categoria', 'CATEGORIA', 'seção', 'secao'):
            assert imp.coluna_canonica(escrito) == 'categoria'

    def test_coluna_desconhecida_e_ignorada_sem_quebrar(self):
        assert imp.coluna_canonica('observações do chef') is None


class TestConferenciaAntesDeGravar:
    def linhas(self):
        return [
            {'nome': 'Salada Caesar', 'preco': '32,90', 'categoria': 'Saladas'},
            {'nome': '', 'preco': '10,00', 'categoria': 'Saladas'},
            {'nome': 'Suco de Laranja', 'preco': 'a combinar', 'categoria': 'Bebidas'},
            {'nome': 'Água', 'preco': '5', 'categoria': 'Bebidas'},
        ]

    def test_conferencia_separa_o_que_entra_do_que_falhou(self):
        r = imp.conferir(self.linhas())

        assert [p['nome'] for p in r.validos] == ['Salada Caesar', 'Água']
        assert len(r.erros) == 2

    def test_cada_erro_diz_a_LINHA_e_o_motivo_em_portugues(self):
        """'Erro na importação' não ajuda ninguém a corrigir a planilha."""
        r = imp.conferir(self.linhas())

        por_linha = {e.linha: e.motivo for e in r.erros}
        assert 3 in por_linha and 4 in por_linha       # 1 é o cabeçalho
        assert 'nome' in por_linha[3].lower()
        assert 'preço' in por_linha[4].lower()
        assert 'traceback' not in str(r.erros).lower()

    def test_arquivo_vazio_nao_e_erro_de_sistema(self):
        r = imp.conferir([])
        assert r.validos == [] and r.erros == []

    def test_o_mesmo_produto_duas_vezes_na_planilha_entra_uma_so(self):
        """Copiar e colar linha é o erro mais comum de quem monta planilha."""
        r = imp.conferir([
            {'nome': 'Coca-Cola', 'preco': '8,00', 'categoria': 'Bebidas'},
            {'nome': 'coca-cola ', 'preco': '8,00', 'categoria': 'Bebidas'},
        ])
        assert len(r.validos) == 1
        assert len(r.erros) == 1
        assert 'repetid' in r.erros[0].motivo.lower()


# ── Gravação: o passo que toca o banco ──────────────────────────────────────

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreProduct

User = get_user_model()


class GravarImportacaoTests(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono-imp', password='x', email='dono-imp@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Import', slug='loja-import', owner=self.dono, status='active',
        )

    def _gravar(self, linhas):
        return imp.gravar(self.store, imp.conferir(linhas).validos, criado_por=self.dono)

    def test_cria_produto_e_a_categoria_pelo_nome(self):
        """Exigir categoria cadastrada antes seria mandar fazer à mão
        exatamente o que o importador veio automatizar."""
        r = self._gravar([{'nome': 'Salada Caesar', 'preco': '32,90', 'categoria': 'Saladas'}])

        p = StoreProduct.objects.get(store=self.store, name='Salada Caesar')
        assert p.price == Decimal('32.90')
        assert p.category is not None and p.category.name == 'Saladas'
        assert r['criados'] == 1 and r['atualizados'] == 0

    def test_reimportar_ATUALIZA_em_vez_de_duplicar(self):
        """O dono vai corrigir a planilha e subir de novo. Se isso duplicar,
        ele termina com o cardápio em dobro e tem que apagar um a um."""
        self._gravar([{'nome': 'Água', 'preco': '5,00', 'categoria': 'Bebidas'}])
        r = self._gravar([{'nome': 'Água', 'preco': '6,50', 'categoria': 'Bebidas'}])

        assert StoreProduct.objects.filter(store=self.store, name='Água').count() == 1
        assert StoreProduct.objects.get(store=self.store, name='Água').price == Decimal('6.50')
        assert r['criados'] == 0 and r['atualizados'] == 1

    def test_categoria_existente_e_reaproveitada(self):
        StoreCategory.objects.create(store=self.store, name='Bebidas', slug='bebidas')
        self._gravar([{'nome': 'Suco', 'preco': '9,00', 'categoria': 'bebidas'}])

        assert StoreCategory.objects.filter(store=self.store, name__iexact='bebidas').count() == 1

    def test_produto_sem_categoria_entra_mesmo_assim(self):
        """Cardápio sem seção é comum em loja pequena. Recusar seria inventar
        uma exigência que o cadastro manual não faz."""
        self._gravar([{'nome': 'Item solto', 'preco': '10,00', 'categoria': ''}])
        assert StoreProduct.objects.filter(store=self.store, name='Item solto').exists()

    def test_nao_toca_em_produto_de_OUTRA_loja_com_o_mesmo_nome(self):
        outra = Store.objects.create(
            name='Outra', slug='outra-imp', owner=self.dono, status='active',
        )
        StoreProduct.objects.create(store=outra, name='Água', price=Decimal('99.00'))

        self._gravar([{'nome': 'Água', 'preco': '5,00', 'categoria': 'Bebidas'}])

        assert StoreProduct.objects.get(store=outra, name='Água').price == Decimal('99.00')


class EndpointDeImportacaoTests(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono-ep', password='x', email='dono-ep@real.com',
        )
        self.store = Store.objects.create(
            name='Loja EP', slug='loja-ep', owner=self.dono, status='active',
        )
        self.client.force_authenticate(user=self.dono)
        self.url = f'/api/v1/stores/{self.store.slug}/produtos/importar/'

    CSV = (
        'Nome,Preço,Categoria\n'
        'Salada Caesar,"32,90",Saladas\n'
        ',"10,00",Saladas\n'
        'Água,5,Bebidas\n'
    )

    def test_conferir_NAO_grava_nada(self):
        """O dono vê o que vai entrar antes de qualquer escrita. Importar 80
        produtos errados é pior que não importar."""
        r = self.client.post(self.url, {'csv': self.CSV, 'confirmar': False}, format='json')

        assert r.status_code == 200, r.data
        assert len(r.data['validos']) == 2
        assert len(r.data['erros']) == 1
        assert StoreProduct.objects.filter(store=self.store).count() == 0

    def test_confirmar_grava(self):
        r = self.client.post(self.url, {'csv': self.CSV, 'confirmar': True}, format='json')

        assert r.status_code in (200, 201), r.data
        assert r.data['criados'] == 2
        assert StoreProduct.objects.filter(store=self.store).count() == 2

    def test_quem_nao_e_da_loja_nao_importa(self):
        intruso = User.objects.create_user(username='intruso-ep', password='x', email='i-ep@real.com')
        self.client.force_authenticate(user=intruso)

        r = self.client.post(self.url, {'csv': self.CSV, 'confirmar': True}, format='json')

        assert r.status_code in (403, 404), r.data
        assert StoreProduct.objects.filter(store=self.store).count() == 0

    def test_csv_vazio_responde_sem_explodir(self):
        r = self.client.post(self.url, {'csv': '', 'confirmar': False}, format='json')
        assert r.status_code == 400
        assert 'planilha' in str(r.data).lower() or 'arquivo' in str(r.data).lower()
