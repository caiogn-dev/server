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


class LojaAntigaSegueNoManualTests(TestCase):
    """Loja grandfather continua no número digitado — decisão do dono em 22/09.

    A exigência de conectar a WABA existe para CLIENTE NOVO: é ela que faz a
    conta de mensagem da Meta ficar com quem vende, e não com a plataforma.
    Loja pré-SaaS é atendida pelo próprio dono, no aparelho dele; exigir
    embedded signup ali seria criar trabalho sem destravar nada.

    `billing_exempt` já é a marca de "as regras do SaaS não valem para esta
    loja" e é o que `billing.is_billing_exempt()` usa. Inventar uma segunda
    flag para o mesmo conceito criaria duas verdades sobre quem é legado.
    """

    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono-velho', password='x', email='velho@real.com',
        )

    def _loja(self, slug, exempt):
        return Store.objects.create(
            name=slug, slug=slug, owner=self.dono, status='active',
            billing_exempt=exempt, whatsapp_number='63999990000',
        )

    def test_loja_grandfather_cumpre_o_passo_so_com_o_numero(self):
        assert _passo(self._loja('velha', True), 'whatsapp')['done'] is True

    def test_cliente_novo_continua_tendo_que_conectar(self):
        assert _passo(self._loja('nova', False), 'whatsapp')['done'] is False

    def test_grandfather_SEM_numero_nenhum_nao_passa(self):
        """Isentar de conectar não é isentar de ter WhatsApp."""
        loja = self._loja('velha-sem', True)
        loja.whatsapp_number = ''
        loja.save(update_fields=['whatsapp_number'])

        assert _passo(loja, 'whatsapp')['done'] is False
