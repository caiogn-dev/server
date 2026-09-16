"""Dia fechado não pode ser anunciado como aberto.

Incidente 16/set, conversa da Elizandra na Cê Saladas: ela perguntou "vocês
atendem até que horas" e o bot respondeu listando *Sábado: 08:00 às 17:00* e
*Domingo: 08:00 às 17:00* — dois dias em que a loja não abre.

O dado no banco estava CERTO: sábado e domingo têm `is_open: false`. O que eles
também têm, e sempre tiveram, é `open`/`close` preenchidos — o painel guarda o
horário mesmo do dia fechado, para não perder a configuração quando o lojista
reabre o dia. `BusinessHoursHandler` testava só `if day_hours:` (dict não-vazio
é verdadeiro) e nunca olhava `is_open`.

O segundo defeito é da mesma função: `datetime.now()` sem timezone, num
container que roda em UTC. Das 21h à meia-noite em Brasília o bot anunciava o
horário do DIA SEGUINTE.
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store
from apps.whatsapp.intents.handlers.info import BusinessHoursHandler

User = get_user_model()

HORARIO_CE_SALADAS = {
    'monday':    {'open': '08:00', 'close': '17:00', 'is_open': True},
    'tuesday':   {'open': '08:00', 'close': '17:00', 'is_open': True},
    'wednesday': {'open': '08:00', 'close': '17:00', 'is_open': True},
    'thursday':  {'open': '08:00', 'close': '17:00', 'is_open': True},
    'friday':    {'open': '08:00', 'close': '17:00', 'is_open': True},
    'saturday':  {'open': '08:00', 'close': '17:00', 'is_open': False},
    'sunday':    {'open': '08:00', 'close': '17:00', 'is_open': False},
}


class HorarioFechadoNoBotTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono_horario', email='dono@horario.com', password='x'
        )
        self.loja = Store.objects.create(
            name='Loja Horario', slug='loja-horario', owner=self.dono,
            status='active', operating_hours=HORARIO_CE_SALADAS,
        )

    def _responder(self):
        handler = BusinessHoursHandler.__new__(BusinessHoursHandler)
        handler.account = MagicMock()
        handler.conversation = MagicMock()
        handler.company_profile = None
        handler._whatsapp_service = None
        handler.store = self.loja
        return handler.handle({}).response_text

    def test_dia_fechado_nao_aparece_com_horario(self):
        texto = self._responder()
        self.assertNotIn('Sábado: 08:00', texto)
        self.assertNotIn('Domingo: 08:00', texto)

    def test_dia_fechado_aparece_como_fechado(self):
        texto = self._responder()
        self.assertIn('Sábado: Fechado', texto)
        self.assertIn('Domingo: Fechado', texto)

    def test_dia_aberto_continua_com_horario(self):
        """Âncora: se tudo virasse 'Fechado', os asserts acima passariam vazios."""
        texto = self._responder()
        self.assertIn('Segunda: 08:00 às 17:00', texto)
        self.assertIn('Sexta: 08:00 às 17:00', texto)

    def test_hoje_fechado_nao_anuncia_horario(self):
        """Num sábado, 'Horário de hoje' não pode dizer 08:00 às 17:00."""
        import apps.whatsapp.intents.handlers.info as info

        sabado = __import__('datetime').datetime(2026, 9, 19, 10, 0)  # sábado
        with patch.object(info, '_agora_da_loja', return_value=sabado):
            texto = self._responder()
        self.assertIn('Horário de hoje', texto)
        self.assertNotIn('Horário de hoje (Sábado):*\n08:00 às 17:00', texto)

    def test_usa_o_fuso_da_loja_e_nao_o_do_servidor(self):
        """Container roda em UTC. 23h de quarta em Brasília é 02h de QUINTA em
        UTC — o bot anunciava o dia errado nas últimas 3 horas do dia."""
        import apps.whatsapp.intents.handlers.info as info

        self.assertTrue(
            hasattr(info, '_agora_da_loja'),
            'a hora tem que vir do fuso da loja, não de datetime.now() naive',
        )


class HorarioComJsonDoPainelTest(TestCase):
    """O JSON do painel nem sempre traz `is_open` como bool.

    `Store._verdadeiro` já sabia disso desde antes: conforme o formulário, o
    valor chega como `False`, `"false"` ou `0`. Uma segunda implementação da
    mesma regra no bot voltaria a errar nos dois últimos — e erraria calada,
    porque `bool("false")` é True.
    """

    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono_json', email='dono@json.com', password='x'
        )

    def _loja_com(self, valor_de_is_open, slug):
        horarios = {dia: dict(h) for dia, h in HORARIO_CE_SALADAS.items()}
        horarios['saturday']['is_open'] = valor_de_is_open
        return Store.objects.create(
            name='L', slug=slug, owner=self.dono, status='active',
            operating_hours=horarios,
        )

    def _responder(self, loja):
        handler = BusinessHoursHandler.__new__(BusinessHoursHandler)
        handler.account = MagicMock()
        handler.conversation = MagicMock()
        handler.company_profile = None
        handler._whatsapp_service = None
        handler.store = loja
        return handler.handle({}).response_text

    def test_is_open_string_false_fecha_o_dia(self):
        texto = self._responder(self._loja_com('false', 'json-str-false'))
        self.assertIn('Sábado: Fechado', texto)

    def test_is_open_zero_fecha_o_dia(self):
        texto = self._responder(self._loja_com(0, 'json-zero'))
        self.assertIn('Sábado: Fechado', texto)

    def test_is_open_string_true_abre_o_dia(self):
        """Âncora: o parser não pode fechar tudo."""
        texto = self._responder(self._loja_com('true', 'json-str-true'))
        self.assertIn('Sábado: 08:00 às 17:00', texto)


class AgendamentoNaoOfereceDiaFechadoTest(TestCase):
    """Terceira cópia da mesma regra: `_next_open_slots`.

    Ele monta a lista de horários para agendar lendo `open`/`close` e pulando
    só o dia SEM configuração (`if not hours: continue`). Dia configurado e
    desligado passava direto — o cliente recebia "Sáb 19/09 08:00" para uma
    loja que não abre no sábado.
    """

    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono_slots', email='dono@slots.com', password='x'
        )
        self.loja = Store.objects.create(
            name='Loja Slots', slug='loja-slots', owner=self.dono,
            status='active', operating_hours=HORARIO_CE_SALADAS,
        )

    def _slots(self):
        from apps.whatsapp.intents.handlers.interactive import (
            InteractiveReplyHandler,
        )

        handler = InteractiveReplyHandler.__new__(InteractiveReplyHandler)
        handler.account = MagicMock()
        handler.conversation = MagicMock()
        handler.company_profile = None
        handler._whatsapp_service = None
        handler.store = self.loja
        return handler._next_open_slots(max_slots=60)

    def test_nao_oferece_horario_em_dia_fechado(self):
        rotulos = [s['title'] for s in self._slots()]
        self.assertNotIn('Sáb', ' '.join(rotulos))
        self.assertNotIn('Dom', ' '.join(rotulos))

    def test_oferece_horario_em_dia_aberto(self):
        """Âncora: se a lista viesse vazia, o assert acima não provaria nada."""
        self.assertGreater(len(self._slots()), 0)
