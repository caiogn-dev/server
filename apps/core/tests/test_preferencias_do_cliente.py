"""As preferências de notificação do cliente têm que existir de verdade.

O CASO REAL (04/09): "cliquei em notificação push para habilitar, e ao salvar,
volta desativada".

A causa não era o salvamento: `preferences` NÃO EXISTIA no backend. O `PATCH`
nunca lia a chave, o `GET` nunca devolvia, e a tela — que recarrega do perfil
depois de salvar — voltava para o padrão. E ainda exibia "Preferências salvas
com sucesso!", porque a requisição respondia 200: o servidor simplesmente
ignorava o campo em silêncio.

Eram três interruptores que não controlavam nada. Nenhum lugar do sistema lia
`notifications_email`, `notifications_whatsapp` ou `notifications_push` — zero
ocorrências fora do próprio formulário.

DECISÃO SOBRE CADA UM, porque persistir sem honrar só faria o botão mentir de
forma mais convincente:

  whatsapp  HONRADO. É o único canal real: o aviso de status do pedido sai por
            ele. Passa a ser consultado antes de enviar.

  push      REMOVIDO da tela. Não existe infraestrutura de push neste sistema
            — nem chave, nem service worker, nem envio. Interruptor de canal
            inexistente é a mesma mentira, só que mais cara de descobrir.

  email     Continua existindo, mas quem manda é o descadastro do e-mail
            marketing (`Subscriber.status`), que já existe e é o mecanismo
            legal (link no rodapé). Duas fontes de verdade sobre a mesma
            decisão do cliente é como uma delas fica errada.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import UserProfile

User = get_user_model()

URL = '/api/v1/core/users/profile/'


class PreferenciasDoClienteTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='cliente-prefs', email='cliente@teste.local', password='x',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _salvar(self, preferences):
        return self.client.patch(URL, {'preferences': preferences}, format='json')

    # ── o bug relatado ──────────────────────────────────────────────────

    def test_o_que_foi_salvo_volta_no_perfil(self):
        """O sintoma exato: salvar e a tela reler o valor antigo."""
        self._salvar({'notifications_whatsapp': False})

        self.assertIs(
            self.client.get(URL).data['preferences']['notifications_whatsapp'], False,
        )

    def test_persiste_de_verdade_no_banco(self):
        self._salvar({'notifications_whatsapp': False})

        perfil = UserProfile.objects.get(user=self.user)
        self.assertIs(perfil.preferences['notifications_whatsapp'], False)

    def test_o_patch_devolve_o_valor_novo_na_hora(self):
        """A tela usa a resposta do PATCH; devolver o antigo já reverte ali."""
        r = self._salvar({'notifications_whatsapp': False})

        self.assertIs(r.data['preferences']['notifications_whatsapp'], False)

    def test_perfil_novo_nao_quebra_sem_preferencia(self):
        self.assertEqual(self.client.get(URL).data['preferences'], {})

    def test_salvar_outro_campo_nao_apaga_as_preferencias(self):
        """PATCH parcial: mexer no nome não pode zerar o que o cliente escolheu."""
        self._salvar({'notifications_whatsapp': False})

        self.client.patch(URL, {'first_name': 'Ana'}, format='json')

        perfil = UserProfile.objects.get(user=self.user)
        self.assertIs(perfil.preferences['notifications_whatsapp'], False)

    def test_uma_preferencia_nova_nao_apaga_as_outras(self):
        self._salvar({'notifications_whatsapp': False})

        self._salvar({'preferred_payment': 'dinheiro'})

        perfil = UserProfile.objects.get(user=self.user)
        self.assertIs(perfil.preferences['notifications_whatsapp'], False)
        self.assertEqual(perfil.preferences['preferred_payment'], 'dinheiro')

    def test_preferencia_precisa_ser_um_objeto(self):
        """Lista ou texto aqui corromperia a leitura de quem consome depois."""
        self.assertEqual(
            self.client.patch(URL, {'preferences': 'sim'}, format='json').status_code, 400,
        )

    def test_um_cliente_nao_ve_a_preferencia_do_outro(self):
        self._salvar({'notifications_whatsapp': False})
        outro = User.objects.create_user(username='outro-cliente', password='x')
        self.client.force_authenticate(outro)

        self.assertEqual(self.client.get(URL).data['preferences'], {})
