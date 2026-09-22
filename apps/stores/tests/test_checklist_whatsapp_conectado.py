"""O checklist não pode dar por pronto um WhatsApp que não conecta nada.

Medido em 22/09: o passo `whatsapp` olhava `store.whatsapp_number` — um campo
de TEXTO que o dono digita. Resultado em produção:

    agriao-comida-saudavel   numero 63999547790     WABA: nenhuma
    ivoneth-banqueteria      numero 5563999547790   WABA: nenhuma
    kero-kero                numero 63992332803     WABA: nenhuma
    solo-e-zelo              numero 21998039194     WABA: nenhuma

Quatro de seis lojas com o passo VERDE e o bot sem poder rodar. A Solo e Zelo
é o caso que fecha o argumento: o "número" dela, `21998039194`, é o mesmo
valor do `waba_id` quebrado daquela conta — alguém colou no campo errado e
nada acusou, porque o checklist só perguntava "tem texto aqui?".

O passo existe para responder "esta loja consegue atender pelo WhatsApp?".
A resposta é a conta conectada, não o número escrito.

Isto é pré-condição de volume, não detalhe: quem conecta a própria WABA paga
as próprias mensagens da Meta (a Pastita já é o caso funcionando). Enquanto o
checklist mentir, ninguém é obrigado a conectar.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store
from apps.stores.services.onboarding_checklist import build_checklist
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


def _passo(store, chave):
    return next(p for p in build_checklist(store)['steps'] if p['key'] == chave)


class ChecklistWhatsAppTests(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono-wpp', password='x', email='dono-wpp@real.com',
        )
        self.store = Store.objects.create(
            name='Loja WPP', slug='loja-wpp', owner=self.dono, status='active',
        )

    def test_numero_digitado_NAO_conta_como_whatsapp_pronto(self):
        self.store.whatsapp_number = '63999547790'
        self.store.save(update_fields=['whatsapp_number'])

        assert _passo(self.store, 'whatsapp')['done'] is False

    def test_conta_conectada_conta(self):
        conta = WhatsAppAccount.objects.create(
            name='Loja WPP', waba_id='123', phone_number_id='456',
            phone_number='+5563999547790', owner=self.dono, is_active=True,
        )
        conta.stores.add(self.store)

        assert _passo(self.store, 'whatsapp')['done'] is True

    def test_conta_DESATIVADA_nao_conta(self):
        """Conta caída (COEX DISCONNECTED, token revogado) não atende ninguém.
        Dar o passo por pronto esconderia justamente a queda."""
        conta = WhatsAppAccount.objects.create(
            name='Loja WPP', waba_id='123', phone_number_id='456',
            phone_number='+5563999547790', owner=self.dono, is_active=False,
        )
        conta.stores.add(self.store)

        assert _passo(self.store, 'whatsapp')['done'] is False

    def test_conta_de_OUTRA_loja_nao_conta(self):
        outra = Store.objects.create(
            name='Outra WPP', slug='outra-wpp', owner=self.dono, status='active',
        )
        conta = WhatsAppAccount.objects.create(
            name='Outra', waba_id='999', phone_number_id='888',
            phone_number='+5563000000000', owner=self.dono, is_active=True,
        )
        conta.stores.add(outra)

        assert _passo(self.store, 'whatsapp')['done'] is False

    def test_o_rotulo_diz_o_que_fazer(self):
        """'Informar WhatsApp' pede para digitar; o que se pede é conectar."""
        rotulo = _passo(self.store, 'whatsapp')['label'].lower()
        assert 'conectar' in rotulo or 'conecte' in rotulo
        assert 'informar' not in rotulo
