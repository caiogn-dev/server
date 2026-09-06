"""Fundir as contas que são a mesma pessoa, sem perder dado nem quebrar chave.

O CASO REAL (05/09): 8 pessoas com 17 contas. Todas pelo mesmo motivo — o
WhatsApp entrega o número sem o nono dígito e o site grava com ele, então a
mesma pessoa entrou duas vezes e virou dois logins.

O dono decidiu: "apenas pegue os dados e tire o dedup". Fundir tudo,
preservando o melhor dado de cada conta.

QUEM SOBREVIVE: mais pedidos PAGOS. Empate decide pelo mais antigo, que é o
"cliente desde" que os relatórios já contam.

POR QUE NÃO "A MAIS ANTIGA VENCE": a conta nova costuma ter o dado melhor. A
Yasmine tem `yas-17@hotmail.com` na conta de agosto e `84195663@local.invalid`
— placeholder interno — na de agosto anterior. Mesma coisa na Elisângela. Quem
vence é decidido pelo histórico; o dado bom migra para ela, venha de onde vier.

AS ARMADILHAS DE CHAVE, que é onde uma fusão ingênua corrompe o banco:

  StoreCustomer       unique(store, user) e unique(store, phone). As duas
                      contas podem ter cadastro na MESMA loja: repontar
                      estoura. Tem que fundir a linha, somando contadores.
  StoreLoyaltyAccount unique(store, user). Mesma coisa, e aqui é saldo de
                      carimbo: somar, não descartar.
  StoreCart           unique de carrinho ativo por (user, store).
  Store.owner         duas das contas são donas de loja de teste. Repontar,
                      nunca deletar sem repontar — apagaria a loja junto.

O QUE NÃO PODE ACONTECER, em nenhuma hipótese: pedido pago ficar órfão ou
mudar de dono. É a memória de compra do cliente e a receita da loja.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import UserProfile
from apps.core.services.fusao_de_contas import FusaoDeContas
from apps.stores.models import Store, StoreOrder
from apps.stores.models.customer import StoreCustomer

User = get_user_model()


class FusaoDeContasTest(TestCase):
    """Testa o conserto de um estado que o banco HOJE não deixa mais existir.

    A trava `uma_conta_por_telefone` (05/09) impede a duplicata de nascer — que
    é o objetivo. Mas a fusão existe justamente para limpar o passado, e o
    passado não pode mais ser construído com a trava de pé.

    Por isso ela cai aqui dentro. A queda vive na transação do teste e some no
    rollback: nenhum outro teste, e muito menos produção, fica sem a trava.

    A alternativa seria testar a fusão com dados que não colidem — o que
    testaria outra coisa e deixaria o conserto sem cobertura no dia em que
    alguém restaurasse um dump antigo.
    """

    def setUp(self):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('DROP INDEX IF EXISTS uma_conta_por_telefone')

        dono = User.objects.create_user(username='dona-fusao', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-fusao', owner=dono,
            store_type='food', status='active',
        )

    def _conta(self, username, telefone, *, email='', nome='', quando=None):
        user = User.objects.create_user(username=username, password='x', email=email)
        if nome:
            partes = nome.split(' ', 1)
            user.first_name = partes[0]
            user.last_name = partes[1] if len(partes) > 1 else ''
            user.save(update_fields=['first_name', 'last_name'])
        if quando:
            User.objects.filter(pk=user.pk).update(date_joined=quando)
        UserProfile.objects.update_or_create(user=user, defaults={'phone': telefone})
        return User.objects.get(pk=user.pk)

    def _pedido(self, user, pago=True, total='50.00'):
        return StoreOrder.objects.create(
            store=self.store, customer=user,
            customer_name='Cliente', customer_phone='5563984195663',
            subtotal=Decimal(total), total=Decimal(total),
            status='delivered' if pago else 'pending',
            payment_status='paid' if pago else 'pending',
        )

    # ── quem sobrevive ──────────────────────────────────────────────────

    def test_vence_quem_tem_mais_pedidos_pagos(self):
        antiga = self._conta('cliente_556384195663', '556384195663')
        nova = self._conta('cliente_5563984195663', '5563984195663')
        self._pedido(antiga)
        self._pedido(nova)
        self._pedido(nova)

        [plano] = FusaoDeContas.planejar()

        self.assertEqual(plano.fica.id, nova.id)

    def test_a_conta_nova_pode_vencer(self):
        """"Mais antiga vence" perderia o e-mail real da Yasmine."""
        antiga = self._conta('cliente_556384195663', '556384195663',
                             email='84195663@local.invalid')
        nova = self._conta('cliente_5563984195663', '5563984195663',
                           email='yas-17@hotmail.com')
        self._pedido(nova)

        [plano] = FusaoDeContas.planejar()

        self.assertEqual(plano.fica.id, nova.id)

    # ── o dado bom migra, venha de onde vier ────────────────────────────

    def test_o_email_de_verdade_migra_para_quem_fica(self):
        vencedora = self._conta('cliente_5563984195663', '5563984195663',
                                email='84195663@local.invalid')
        self._pedido(vencedora)
        self._conta('cliente_556384195663', '556384195663', email='yas-17@hotmail.com')

        FusaoDeContas.aplicar(FusaoDeContas.planejar())

        vencedora.refresh_from_db()
        self.assertEqual(vencedora.email, 'yas-17@hotmail.com')

    def test_nao_troca_email_real_por_placeholder(self):
        vencedora = self._conta('a', '5563984195663', email='real@gmail.com')
        self._pedido(vencedora)
        self._conta('b', '556384195663', email='84195663@local.invalid')

        FusaoDeContas.aplicar(FusaoDeContas.planejar())

        vencedora.refresh_from_db()
        self.assertEqual(vencedora.email, 'real@gmail.com')

    def test_o_nome_melhor_migra(self):
        vencedora = self._conta('a', '5563984195663', nome='Yasmine')
        self._pedido(vencedora)
        self._conta('b', '556384195663', nome='Yasmine Ulisses')

        FusaoDeContas.aplicar(FusaoDeContas.planejar())

        vencedora.refresh_from_db()
        self.assertEqual(f'{vencedora.first_name} {vencedora.last_name}'.strip(), 'Yasmine Ulisses')

    def test_nome_estilizado_do_whatsapp_perde_para_o_nome_de_verdade(self):
        """O caso da Elisângela.

        A conta que vence tem o nome como ela escreveu no WhatsApp:
        "𝑬𝒍𝒊𝒔â𝒏𝒈𝒆𝒍𝒂 ®️𝒖𝒑𝒑𝒆𝒏𝒕𝒉𝒂𝒍" — letras matemáticas do Unicode, que não são
        letras comuns. É mais LONGO que "Elisângela Ruppenthal", então uma
        regra de tamanho o manteria no painel para sempre, e ninguém consegue
        buscar por ele.
        """
        vencedora = self._conta('a', '5563984195663', nome='𝑬𝒍𝒊𝒔â𝒏𝒈𝒆𝒍𝒂 ®️𝒖𝒑𝒑𝒆𝒏𝒕𝒉𝒂𝒍')
        self._pedido(vencedora)
        self._conta('b', '556384195663', nome='Elisângela Ruppenthal')

        FusaoDeContas.aplicar(FusaoDeContas.planejar())

        vencedora.refresh_from_db()
        self.assertEqual(
            f'{vencedora.first_name} {vencedora.last_name}'.strip(),
            'Elisângela Ruppenthal',
        )

    def test_acento_conta_como_letra_normal(self):
        """"Gonçalves" não pode perder para um nome sem acento por causa disso."""
        vencedora = self._conta('a', '5563984195663', nome='Ivo')
        self._pedido(vencedora)
        self._conta('b', '556384195663', nome='Ivoneth Gonçalves')

        FusaoDeContas.aplicar(FusaoDeContas.planejar())

        vencedora.refresh_from_db()
        self.assertEqual(
            f'{vencedora.first_name} {vencedora.last_name}'.strip(),
            'Ivoneth Gonçalves',
        )

    # ── o que NÃO pode acontecer ────────────────────────────────────────

    def test_nenhum_pedido_pago_fica_orfao(self):
        vencedora = self._conta('a', '5563984195663')
        perdedora = self._conta('b', '556384195663')
        self._pedido(vencedora)
        do_perdedor = self._pedido(perdedora)

        FusaoDeContas.aplicar(FusaoDeContas.planejar())

        do_perdedor.refresh_from_db()
        self.assertEqual(do_perdedor.customer_id, vencedora.id)
        self.assertEqual(StoreOrder.objects.filter(customer__isnull=True).count(), 0)

    def test_a_conta_perdedora_some(self):
        vencedora = self._conta('a', '5563984195663')
        perdedora = self._conta('b', '556384195663')
        self._pedido(vencedora)

        FusaoDeContas.aplicar(FusaoDeContas.planejar())

        self.assertFalse(User.objects.filter(pk=perdedora.pk).exists())
        self.assertTrue(User.objects.filter(pk=vencedora.pk).exists())

    def test_cadastro_na_mesma_loja_e_fundido_e_nao_duplicado(self):
        """unique(store, user): repontar o cadastro do perdedor estouraria.

        O telefone dos dois não pode ser igual — a trava
        `cliente_unico_por_telefone_na_loja` (04/09) já impede. A colisão que
        sobra é esta: cadastro do perdedor SEM telefone (vazio é a exceção da
        trava) na mesma loja onde o vencedor já tem o dele.
        """
        vencedora = self._conta('a', '5563984195663')
        perdedora = self._conta('b', '556384195663')
        self._pedido(vencedora)
        StoreCustomer.objects.create(store=self.store, user=vencedora,
                                     phone='5563984195663', total_orders=2,
                                     total_spent=Decimal('100'))
        StoreCustomer.objects.create(store=self.store, user=perdedora,
                                     phone='', total_orders=1,
                                     total_spent=Decimal('50'))

        FusaoDeContas.aplicar(FusaoDeContas.planejar())

        restantes = StoreCustomer.objects.filter(store=self.store)
        self.assertEqual(restantes.count(), 1)
        self.assertEqual(restantes.first().total_orders, 3)
        self.assertEqual(restantes.first().total_spent, Decimal('150'))

    def test_a_loja_do_perdedor_muda_de_dono_em_vez_de_sumir(self):
        vencedora = self._conta('a', '5563984195663')
        perdedora = self._conta('b', '556384195663')
        self._pedido(vencedora)
        minha = Store.objects.create(
            billing_exempt=True, name='Testezaço', slug='testezaco-fusao',
            owner=perdedora, store_type='food', status='active',
        )

        FusaoDeContas.aplicar(FusaoDeContas.planejar())

        minha.refresh_from_db()
        self.assertEqual(minha.owner_id, vencedora.id)

    def test_pessoas_diferentes_nao_sao_tocadas(self):
        a = self._conta('a', '5563984195663')
        b = self._conta('b', '5563992618115')

        self.assertEqual(FusaoDeContas.planejar(), [])
        self.assertTrue(User.objects.filter(pk=a.pk).exists())
        self.assertTrue(User.objects.filter(pk=b.pk).exists())

    def test_planejar_nao_escreve_nada(self):
        self._conta('a', '5563984195663')
        perdedora = self._conta('b', '556384195663')

        FusaoDeContas.planejar()

        self.assertTrue(User.objects.filter(pk=perdedora.pk).exists())


class DominiosInternosTest(TestCase):
    """A lista de e-mails inventados precisa estar completa.

    Um domínio que falta na lista passa por endereço de verdade e DESCARTA o
    e-mail real da pessoa na fusão. Aconteceu com `@whatsapp.bot` em 05/09: a
    Elisângela perdeu `eliruppenthal@hotmail.com` porque o endereço inventado
    da outra conta dela foi considerado legítimo.

    Esta peneira lê os e-mails que o próprio sistema gera.
    """

    def test_todo_dominio_que_o_sistema_inventa_esta_na_lista(self):
        from apps.core.services.fusao_de_contas import _email_de_verdade

        inventados = [
            '5563992957931@pastita.local',
            '92957931@local.invalid',
            'whatsapp_556399619019@whatsapp.bot',
            'cliente@anonimizado.local',
        ]
        for email in inventados:
            self.assertFalse(_email_de_verdade(email), f'{email} passou por real')

    def test_endereco_de_verdade_continua_valendo(self):
        from apps.core.services.fusao_de_contas import _email_de_verdade

        for email in ['eliruppenthal@hotmail.com', 'yas-17@hotmail.com',
                      'zaniadosanjossilva@icloud.com']:
            self.assertTrue(_email_de_verdade(email), f'{email} foi tratado como inventado')


class UmaContaPorTelefoneTest(TestCase):
    """A trava que impede a duplicação de voltar.

    Fundir 9 contas resolveu o passado. Sem trava, o futuro se repete: são
    vários caminhos que criam usuário (OTP do WhatsApp, checkout do site,
    painel, importação) e basta um esquecer de procurar antes de criar.

    Foi exatamente assim nas quatro vezes anteriores em que "normalizamos o
    telefone" e o problema voltou. O cadastro de cliente ganhou trava de banco
    em 04/09; esta é a mesma ideia na camada da CONTA.

    Falhar ALTO é o ponto. Um caminho que esqueça a regra recebe IntegrityError
    e alguém conserta; sem a trava ele cria a segunda conta em silêncio e o
    estrago só aparece semanas depois, num relatório que não fecha.
    """

    def test_o_banco_recusa_duas_contas_com_o_mesmo_telefone(self):
        from django.db import IntegrityError, transaction

        primeira = User.objects.create_user(username='primeira-conta', password='x')
        UserProfile.objects.update_or_create(
            user=primeira, defaults={'phone': '5563991124171'},
        )
        segunda = User.objects.create_user(username='segunda-conta', password='x')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserProfile.objects.update_or_create(
                    user=segunda, defaults={'phone': '5563991124171'},
                )

    def test_o_formato_do_whatsapp_colide_com_o_do_site(self):
        """`556391124171` e `5563991124171` são a MESMA pessoa.

        A trava só funciona porque o telefone é gravado na forma canônica: sem
        isso o banco veria dois textos diferentes e deixaria passar.
        """
        from django.db import IntegrityError, transaction

        do_site = User.objects.create_user(username='do-site', password='x')
        UserProfile.objects.update_or_create(
            user=do_site, defaults={'phone': '5563991124171'},
        )
        do_whatsapp = User.objects.create_user(username='do-whatsapp', password='x')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserProfile.objects.update_or_create(
                    user=do_whatsapp, defaults={'phone': '556391124171'},
                )

    def test_varias_contas_sem_telefone_continuam_valendo(self):
        """Conta de painel e de teste não têm telefone. Vazio não colide."""
        for i in range(3):
            u = User.objects.create_user(username=f'sem-telefone-{i}', password='x')
            UserProfile.objects.update_or_create(user=u, defaults={'phone': ''})

        self.assertEqual(UserProfile.objects.filter(phone='').count(), 3)
