"""Regressão: lembrete de PIX e de carrinho nunca chegavam ao cliente.

As tasks procuravam templates por nomes que o seeder nunca criou:

    send_payment_reminder  → 'payment_reminder_1' / 'payment_reminder_2' / 'payment_expired'
    send_cart_reminder     → 'cart_reminder_30'   / 'cart_reminder_2h'   / 'cart_reminder_24h'

O banco de produção tem, nas 9 lojas, apenas os nomes semeados:

    pix_reminder · pix_expired · cart_abandoned

Resultado: `AutoMessage.DoesNotExist` em 100% das tentativas, engolido por um
`logger.warning`. Em 94 pedidos nenhum `payment_reminder_*_sent` foi gravado, e
o log do worker registra "Template cart_reminder_30 not found" a cada ciclo.

`payment_expired` nem existia em `EventType` — era um valor impossível.

A correção resolve o template por lista de preferência: usa o nome específico
quando a loja o tiver, e cai no nome semeado quando não tiver.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import AutoMessage, CompanyProfile
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.tasks.automation_tasks import (
    CART_TEMPLATES,
    PIX_TEMPLATES,
    _resolve_template,
)

User = get_user_model()


class ResolveTemplateSemeadoTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='tpl-owner', email='tpl@t.com', password='x'
        )
        self.account = WhatsAppAccount.objects.create(
            name='loja', phone_number_id='pn-tpl', waba_id='wa-tpl',
            phone_number='+5563999000000', display_phone_number='+5563999000000',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.user,
        )
        # CompanyProfile é auto-criado por signal no post_save do WhatsAppAccount.
        self.profile = CompanyProfile.objects.get(account=self.account)

    def _seed(self, event_type, name):
        return AutoMessage.objects.create(
            company=self.profile,
            event_type=event_type,
            name=name,
            message_text='Oi {customer_name}, faltou pagar {amount}.',
            is_active=True,
        )

    # --- PIX -------------------------------------------------------------

    def test_lembrete_pix_usa_template_semeado_pix_reminder(self):
        """Só existe 'pix_reminder' — era exatamente o caso de produção."""
        semeado = self._seed('pix_reminder', 'Lembrete de PIX')

        for etapa in ('first', 'second'):
            with self.subTest(etapa=etapa):
                achado = _resolve_template(self.profile, PIX_TEMPLATES[etapa])
                self.assertIsNotNone(
                    achado, f'etapa {etapa} não achou template — cliente não recebe nada'
                )
                self.assertEqual(achado.pk, semeado.pk)

    def test_pix_expirado_usa_template_semeado(self):
        semeado = self._seed('pix_expired', 'PIX expirado')
        achado = _resolve_template(self.profile, PIX_TEMPLATES['final'])
        self.assertIsNotNone(achado)
        self.assertEqual(achado.pk, semeado.pk)

    def test_nome_especifico_tem_prioridade_sobre_o_semeado(self):
        """Quem já criou 'payment_reminder_1' continua usando o dele."""
        self._seed('pix_reminder', 'genérico')
        especifico = self._seed('payment_reminder_1', 'específico 30min')

        achado = _resolve_template(self.profile, PIX_TEMPLATES['first'])
        self.assertEqual(achado.pk, especifico.pk)

    def test_template_inativo_e_ignorado(self):
        AutoMessage.objects.create(
            company=self.profile, event_type='pix_reminder', name='desligado',
            message_text='x', is_active=False,
        )
        self.assertIsNone(_resolve_template(self.profile, PIX_TEMPLATES['first']))

    def test_sem_template_nenhum_retorna_none(self):
        self.assertIsNone(_resolve_template(self.profile, PIX_TEMPLATES['first']))

    # --- Carrinho --------------------------------------------------------

    def test_lembrete_carrinho_usa_template_semeado_cart_abandoned(self):
        """O log de produção acusava cart_reminder_30/2h/24h ausentes."""
        semeado = self._seed('cart_abandoned', 'Carrinho abandonado')

        for etapa in ('30min', '2h', '24h'):
            with self.subTest(etapa=etapa):
                achado = _resolve_template(self.profile, CART_TEMPLATES[etapa])
                self.assertIsNotNone(
                    achado, f'etapa {etapa} não achou template — carrinho morre calado'
                )
                self.assertEqual(achado.pk, semeado.pk)

    def test_isolamento_entre_lojas(self):
        """O template de uma loja não pode vazar para outra."""
        self._seed('pix_reminder', 'da loja A')

        outro_user = User.objects.create_user(
            username='tpl-outro', email='o@t.com', password='x'
        )
        outra_conta = WhatsAppAccount.objects.create(
            name='outra', phone_number_id='pn-outro', waba_id='wa-outro',
            phone_number='+5563999111111', display_phone_number='+5563999111111',
            access_token_encrypted='x', webhook_verify_token='x', owner=outro_user,
        )
        outro_profile = CompanyProfile.objects.get(account=outra_conta)

        self.assertIsNone(_resolve_template(outro_profile, PIX_TEMPLATES['first']))
