"""O endereço do pedido é gravado ESTRUTURADO, campo por campo.

Alguns caminhos do checkout gravavam o endereço formatado inteiro dentro de
`street` — às vezes duas vezes:

    street: "Quadra 501 Sul Avenida NS 1, 9, Recepção da ortolife, espaço life
             - Centro, Palmas, TO, 9, Recepção da ortolife, espaço life -
             Centro, Palmas, TO"

Com isso, quem monta a linha de exibição repete bairro e cidade três vezes, e
quem quer só a rua (etiqueta, roteirização, relatório por bairro) não tem como
pegar. O painel aprendeu a limpar na EXIBIÇÃO, mas o dado seguia torto no
banco — e limpar na saída não conserta quem lê direto.

Aqui a estrutura é feita na ENTRADA: cada campo recebe o que é dele.
"""
from apps.stores.services.endereco_estruturado import estruturar_endereco


class TestRuaSuja:
    SUJO = ('Quadra 501 Sul Avenida NS 1, 9, Recepção da ortolife, espaço life'
            ' - Centro, Palmas, TO, 9, Recepção da ortolife, espaço life - Centro, Palmas, TO')

    def test_a_rua_fica_so_com_a_rua(self):
        e = estruturar_endereco({
            'street': self.SUJO, 'number': '9', 'complement': 'Recepção da ortolife, espaço life',
            'neighborhood': 'Centro', 'city': 'Palmas', 'state': 'TO', 'zip_code': '77016006',
        })
        assert e['street'] == 'Quadra 501 Sul Avenida NS 1'

    def test_os_outros_campos_sobrevivem(self):
        e = estruturar_endereco({
            'street': self.SUJO, 'number': '9', 'complement': 'Recepção da ortolife, espaço life',
            'neighborhood': 'Centro', 'city': 'Palmas', 'state': 'TO', 'zip_code': '77016006',
        })
        assert e['number'] == '9'
        assert e['neighborhood'] == 'Centro'
        assert e['city'] == 'Palmas'
        assert e['state'] == 'TO'
        assert e['zip_code'] == '77016006'
        assert e['complement'] == 'Recepção da ortolife, espaço life'

    def test_nada_se_perde_no_caminho(self):
        """Estruturar não pode APAGAR: o texto original fica guardado."""
        e = estruturar_endereco({'street': self.SUJO, 'city': 'Palmas', 'state': 'TO'})
        assert self.SUJO in e['raw_address'] or e['raw_address_original'] == self.SUJO


class TestRuaLimpaNaoEMexida:
    def test_endereco_ja_certo_passa_intacto(self):
        entrada = {
            'street': 'Rua das Palmeiras', 'number': '120', 'complement': 'apto 302',
            'neighborhood': 'Plano Diretor Sul', 'city': 'Palmas', 'state': 'TO',
            'zip_code': '77020024',
        }
        e = estruturar_endereco(entrada)
        for campo, valor in entrada.items():
            assert e[campo] == valor, campo

    def test_rua_com_virgula_legitima_nao_e_cortada(self):
        # "Rua 7, Lote 12" é o nome da rua com uma vírgula — não é sujeira.
        e = estruturar_endereco({'street': 'Rua 7, Lote 12', 'city': 'Palmas'})
        assert e['street'] == 'Rua 7, Lote 12'


class TestPreencheOQueFalta:
    def test_puxa_bairro_e_cidade_de_dentro_da_rua_suja(self):
        """Se o campo está vazio e a informação estava presa na rua, ela vai
        para o lugar certo em vez de sumir junto com o corte."""
        e = estruturar_endereco({
            'street': 'Avenida NS 2, 45 - Plano Diretor Norte, Palmas, TO',
        })
        assert e['street'] == 'Avenida NS 2'
        assert e['number'] == '45'
        assert e['neighborhood'] == 'Plano Diretor Norte'
        assert e['city'] == 'Palmas'
        assert e['state'] == 'TO'

    def test_nao_sobrescreve_o_que_o_cliente_digitou(self):
        e = estruturar_endereco({
            'street': 'Avenida NS 2, 45 - Centro, Palmas, TO',
            'number': '99', 'neighborhood': 'Aureny III',
        })
        assert e['number'] == '99'
        assert e['neighborhood'] == 'Aureny III'


class TestBordas:
    def test_endereco_vazio_nao_quebra(self):
        assert estruturar_endereco({}) == {}
        assert estruturar_endereco(None) == {}

    def test_so_texto_livre_continua_sendo_texto_livre(self):
        e = estruturar_endereco({'raw_address': 'Perto da praça, casa azul'})
        assert e['raw_address'] == 'Perto da praça, casa azul'

    def test_coordenada_e_preservada(self):
        e = estruturar_endereco({'street': 'Rua A', 'lat': '-10.24', 'lng': '-48.35'})
        assert e['lat'] == '-10.24'
        assert e['lng'] == '-48.35'

    def test_raw_address_e_remontado_a_partir_das_partes(self):
        e = estruturar_endereco({
            'street': 'Rua A', 'number': '10', 'neighborhood': 'Centro',
            'city': 'Palmas', 'state': 'TO',
        })
        assert e['raw_address'] == 'Rua A, 10 - Centro, Palmas, TO'
