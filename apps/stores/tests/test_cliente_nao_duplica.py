"""Uma pessoa, um cadastro por loja. Garantido pelo BANCO.

O CASO REAL (04/09): "tem muitos cadastros duplicados na verdade, e já era algo
que estávamos falando e ainda assim continua duplicando... quero solução, sem
workaround nem gambiarra tapa-buraco".

Ele está certo sobre o histórico: já normalizamos telefone em vários pontos e o
problema voltou toda vez. O motivo é que normalizar é uma CONVENÇÃO — depende
de todo caminho novo lembrar dela. São sete caminhos que criam cliente (site,
PDV, bot, link de pagamento, painel, importação, agente), e basta um esquecer.

A DIFERENÇA DESTA VEZ: três camadas, e a última não depende de ninguém lembrar.

  1. UMA FORMA CANÔNICA. `normalize_phone_number` resolve DDI e nono dígito.
     `556391124171` (wa_id) e `5563991124171` (checkout) viram o mesmo texto.

  2. NORMALIZAÇÃO NA ESCRITA, no `save()` do modelo. Não no serviço, não na
     view: no único ponto por onde todos os sete caminhos passam.

  3. UMA TRAVA NO BANCO. `UniqueConstraint(store, phone)`. Um código novo que
     esqueça as duas primeiras camadas recebe IntegrityError e falha ALTO, em
     vez de criar o segundo cadastro em silêncio.

A camada 3 é o que transforma isto de convenção em garantia. Sem ela, esta
correção seria a quarta tentativa da mesma promessa.
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.stores.models import Store
from apps.stores.models.customer import StoreCustomer

User = get_user_model()


class ClienteNaoDuplicaTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-dedup', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-dedup', owner=dono,
            store_type='food', status='active',
        )

    def _cadastro(self, telefone, sufixo):
        user = User.objects.create_user(username=f'cli-{sufixo}', password='x')
        return StoreCustomer.objects.create(store=self.store, user=user, phone=telefone)

    # ── camada 2: normaliza na escrita ──────────────────────────────────

    def test_o_telefone_e_gravado_na_forma_canonica(self):
        cadastro = self._cadastro('63992618115', 'a')

        self.assertEqual(cadastro.phone, '5563992618115')

    def test_o_formato_do_whatsapp_vira_o_mesmo_do_site(self):
        """wa_id vem sem o nono dígito; o checkout grava com ele.

        Zanya e Yeda apareceram duas vezes na lista da Cê exatamente por isto.
        """
        do_whatsapp = self._cadastro('556391124171', 'wa')

        self.assertEqual(do_whatsapp.phone, '5563991124171')

    # ── camada 3: o banco recusa ────────────────────────────────────────

    def test_o_banco_recusa_o_segundo_cadastro_da_mesma_pessoa(self):
        """A garantia. Um caminho novo que esqueça a regra falha ALTO."""
        self._cadastro('5563991124171', 'primeiro')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._cadastro('556391124171', 'segundo')  # mesma pessoa, wa_id

    def test_a_trava_e_por_loja(self):
        """A mesma pessoa PODE ser cliente de duas lojas diferentes."""
        outra = Store.objects.create(
            billing_exempt=True, name='Outra', slug='outra-dedup',
            owner=User.objects.create_user(username='dono2-dedup', password='x'),
            store_type='food', status='active',
        )
        self._cadastro('5563991124171', 'aqui')

        StoreCustomer.objects.create(
            store=outra,
            user=User.objects.create_user(username='cli-la', password='x'),
            phone='5563991124171',
        )

        self.assertEqual(StoreCustomer.objects.filter(phone='5563991124171').count(), 2)

    def test_cadastros_sem_telefone_nao_colidem(self):
        """Cliente de balcão pode não ter telefone; vários '' são válidos."""
        self._cadastro('', 'x')
        self._cadastro('', 'y')

        self.assertEqual(StoreCustomer.objects.filter(store=self.store, phone='').count(), 2)
