from apps.stores.services.voucher import bandeiras


def test_catalogo_tem_valor_e_rotulo():
    assert all({'value', 'label'} <= set(b) for b in bandeiras.CATALOGO)


def test_as_tres_bandeiras_desta_fase_estao_no_catalogo():
    assert set(bandeiras.valores()) == {'vr', 'sodexo', 'ticket'}


def test_alelo_esta_fora_por_ausencia_e_nao_por_if():
    """O Pagar.me fechou novas integracoes com a Alelo. Ela sai do catalogo —
    nao existe `if brand == 'alelo'` em lugar nenhum."""
    assert 'alelo' not in bandeiras.valores()


def test_rotulo_conhecido_vem_do_catalogo():
    assert bandeiras.rotulo('vr') == 'VR Benefícios'


def test_rotulo_desconhecido_nao_explode():
    assert bandeiras.rotulo('xpto') == 'xpto'
