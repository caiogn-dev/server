from apps.stores.services.voucher import bandeiras


def test_catalogo_tem_valor_e_rotulo():
    assert all({'value', 'label'} <= set(b) for b in bandeiras.CATALOGO)


def test_as_tres_bandeiras_do_pagarme():
    assert set(bandeiras.valores('pagarme')) == {'vr', 'sodexo', 'ticket'}


def test_alelo_entra_pelo_trilho_da_cielo_e_nao_do_pagarme():
    """O Pagar.me fechou novas integracoes com a Alelo. Ela e cobrada pela
    API E-commerce da Cielo — e quem decide isso e o campo `trilho` do
    catalogo, nao um `if brand == 'alelo'`."""
    assert 'alelo' not in bandeiras.valores('pagarme')
    assert bandeiras.valores('cielo') == ('alelo',)
    assert bandeiras.trilho('alelo') == 'cielo'


def test_toda_bandeira_integrada_declara_o_trilho():
    assert all(b.get('trilho') for b in bandeiras.CATALOGO)


def test_bandeira_manual_nao_tem_trilho():
    assert bandeiras.trilho('volus') == ''


def test_rotulo_conhecido_vem_do_catalogo():
    assert bandeiras.rotulo('vr') == 'VR Benefícios'


def test_rotulo_desconhecido_nao_explode():
    assert bandeiras.rotulo('xpto') == 'xpto'
