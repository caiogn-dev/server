"""
Configuração do montador (SaladBuilder) por categoria.

O storefront cravava no código os quatro passos da Cê Saladas — slug, rótulo,
máximo de escolhas, obrigatoriedade e quais eram inclusos:

    STEPS = [
      {'base',        max: 1,  required},
      {'proteina',    max: 3},
      {'complemento', max: 20},
      {'molho',       max: 1,  required, included},
    ]

Numa plataforma multi-loja isso é o domínio de UMA loja dentro do produto de
todas. Quem monta pizza, açaí ou marmita precisa dos próprios passos. A
configuração passa a morar na categoria, que é de quem é: a loja.
"""
import pytest
from django.db import IntegrityError

from apps.core.models import User
from apps.stores.models import Store, StoreCategory


pytestmark = pytest.mark.django_db


@pytest.fixture
def store(db):
    dono = User.objects.create_user(
        username='dono-montador', email='dono-montador@example.com', password='x'
    )
    return Store.objects.create(name='Montador', slug='montador', owner=dono)


@pytest.fixture
def outra_store(db):
    dono = User.objects.create_user(
        username='dono-montador-2', email='dono-montador-2@example.com', password='x'
    )
    return Store.objects.create(name='Montador 2', slug='montador-2', owner=dono)


def _limpar_montador_incompleto(StoreCategory):
    """Regra: sem passo na ordem 0, a loja não tem montador. Mesma lógica da 0073."""
    lojas_ok = set(
        StoreCategory.objects
        .filter(builder_step_order=0)
        .values_list('store_id', flat=True)
    )
    StoreCategory.objects.filter(
        builder_step_order__isnull=False
    ).exclude(store_id__in=lojas_ok).update(
        builder_step_order=None,
        builder_max_selections=1,
        builder_required=False,
        builder_included=False,
        builder_expand_variants=False,
    )


def _categoria(store, slug, **kwargs):
    return StoreCategory.objects.create(
        store=store, name=slug.title(), slug=slug, **kwargs
    )


class TestCamposDoMontador:
    def test_categoria_comum_nao_e_passo_do_montador(self, store):
        cat = _categoria(store, 'bebidas')
        # `builder_step_order` nulo é o que diz "não participa do montador".
        assert cat.builder_step_order is None
        assert cat.is_builder_step is False

    def test_categoria_com_ordem_definida_vira_passo(self, store):
        cat = _categoria(store, 'base', builder_step_order=0)
        assert cat.is_builder_step is True

    def test_padroes_sao_conservadores(self, store):
        cat = _categoria(store, 'base', builder_step_order=0)
        # Uma escolha, opcional e cobrada: o mínimo que não inventa regra.
        assert cat.builder_max_selections == 1
        assert cat.builder_required is False
        assert cat.builder_included is False
        assert cat.builder_expand_variants is False

    def test_guarda_a_configuracao_completa_de_um_passo(self, store):
        cat = _categoria(
            store, 'molhos',
            builder_step_order=3,
            builder_max_selections=1,
            builder_required=True,
            builder_included=True,
            builder_expand_variants=True,
        )
        cat.refresh_from_db()
        assert (cat.builder_max_selections, cat.builder_required) == (1, True)
        assert (cat.builder_included, cat.builder_expand_variants) == (True, True)

    def test_maximo_zero_nao_e_aceito(self, store):
        # Passo que não deixa escolher nada não é passo.
        cat = _categoria(store, 'base', builder_step_order=0, builder_max_selections=0)
        with pytest.raises(Exception):
            cat.full_clean()

    def test_passo_do_montador_nao_precisa_ser_escondido_do_cardapio(self, store):
        # Molhos é passo do montador E categoria visível do cardápio: os dois
        # conceitos são independentes e `is_builder_group` continua só sobre
        # esconder da vitrine.
        cat = _categoria(store, 'molhos', builder_step_order=3, is_builder_group=False)
        assert cat.is_builder_step is True
        assert cat.is_builder_group is False


class TestOrdemDosPassos:
    def test_a_ordem_do_montador_e_independente_do_sort_order_da_vitrine(self, store):
        # Na Cê Saladas o sort_order é base=3, complemento=4, proteina=5, mas o
        # montador pergunta base -> proteina -> complemento -> molho.
        _categoria(store, 'base', sort_order=3, builder_step_order=0)
        _categoria(store, 'complemento', sort_order=4, builder_step_order=2)
        _categoria(store, 'proteina', sort_order=5, builder_step_order=1)
        _categoria(store, 'molhos', sort_order=2, builder_step_order=3)

        passos = list(
            StoreCategory.objects
            .filter(store=store, builder_step_order__isnull=False)
            .order_by('builder_step_order')
            .values_list('slug', flat=True)
        )
        assert passos == ['base', 'proteina', 'complemento', 'molhos']

    def test_duas_categorias_nao_ocupam_o_mesmo_passo(self, store):
        _categoria(store, 'base', builder_step_order=0)
        with pytest.raises(IntegrityError):
            _categoria(store, 'outra-base', builder_step_order=0)

    def test_lojas_diferentes_podem_usar_a_mesma_ordem(self, store, outra_store):
        _categoria(store, 'base', builder_step_order=0)
        _categoria(outra_store, 'massa', builder_step_order=0)
        assert StoreCategory.objects.filter(builder_step_order=0).count() == 2


class TestSerializer:
    def test_a_api_entrega_a_configuracao_do_passo(self, store):
        from apps.stores.api.serializers import StoreCategorySerializer

        cat = _categoria(
            store, 'proteina',
            builder_step_order=1, builder_max_selections=3, builder_required=False,
        )
        dados = StoreCategorySerializer(cat).data
        assert dados['builder_step_order'] == 1
        assert dados['builder_max_selections'] == 3
        assert dados['builder_required'] is False
        assert dados['builder_included'] is False
        assert dados['builder_expand_variants'] is False


class TestMontadorPrecisaDoPassoInicial:
    """
    A 0072 traduziu o contrato do código procurando os slugs base/proteina/
    complemento/molhos em TODA loja. Só que "molhos" também existe em loja que
    não monta nada: a Pastita tem molhos como categoria comum e ganhou um passo,
    o que faria o montador aparecer lá com um passo só. Montador sem o passo
    inicial (ordem 0) não é montador.
    """

    def test_loja_que_so_tem_molhos_fica_sem_configuracao(self, store):
        _categoria(store, 'molhos', builder_step_order=3, builder_included=True)
        _limpar_montador_incompleto(StoreCategory)
        assert not StoreCategory.objects.filter(
            store=store, builder_step_order__isnull=False
        ).exists()

    def test_loja_com_passo_inicial_mantem_todos_os_passos(self, store):
        _categoria(store, 'base', builder_step_order=0, builder_required=True)
        _categoria(store, 'molhos', builder_step_order=3, builder_included=True)
        _limpar_montador_incompleto(StoreCategory)
        assert StoreCategory.objects.filter(
            store=store, builder_step_order__isnull=False
        ).count() == 2

    def test_uma_loja_incompleta_nao_derruba_a_outra(self, store, outra_store):
        _categoria(store, 'base', builder_step_order=0)
        _categoria(store, 'molhos', builder_step_order=3)
        _categoria(outra_store, 'molhos', builder_step_order=3)
        _limpar_montador_incompleto(StoreCategory)
        assert StoreCategory.objects.filter(
            store=store, builder_step_order__isnull=False
        ).count() == 2
        assert not StoreCategory.objects.filter(
            store=outra_store, builder_step_order__isnull=False
        ).exists()
