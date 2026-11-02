"""
Segredo não sai da máquina em log nem no GlitchTip, venha de onde vier.

Os testes disparam o erro de verdade: passam pelo logging real e por um cliente
Sentry real com transporte falso, em vez de procurar padrões no código-fonte.
"""
import json
import logging
import time
from unittest import TestCase

import sentry_sdk
from sentry_sdk.envelope import Envelope
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

from apps.core.logging import JsonFormatter, redact_secrets, scrub_sentry_event

MP_TOKEN = 'APP_USR-1234567890123456-110212-abcdef0123456789abcdef0123456789-987654321'
META_TOKEN = 'EAAGm0PX4ZCpsBAKZCZD1234567890abcdefghijklmnop'
NVIDIA_KEY = 'nvapi-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789'
OPENAI_KEY = 'sk-proj-AbCdEfGhIjKlMnOpQrStUvWx'
DRF_TOKEN = '9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b'
TODOS = [MP_TOKEN, META_TOKEN, NVIDIA_KEY, OPENAI_KEY, DRF_TOKEN]


def _formata(logger_call):
    """Roda uma chamada de log real e devolve o JSON que iria para o stdout."""
    saidas = []

    class Captura(logging.Handler):
        def emit(self, record):
            saidas.append(self.format(record))

    logger = logging.getLogger('teste.redacao')
    logger.handlers = []
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    handler = Captura()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger_call(logger)
    assert len(saidas) == 1
    return saidas[0]


class RedactSecretsTest(TestCase):
    def test_tira_segredo_nos_formatos_em_que_ele_aparece(self):
        casos = [
            f'GET https://api.mercadopago.com/v1/x?access_token={MP_TOKEN}&a=1',
            f"401 {{'Authorization': 'Bearer {MP_TOKEN}'}}",
            f'{{"access_token": "{META_TOKEN}", "ok": false}}',
            f'{{\\"access_token\\":\\"{META_TOKEN}\\"}}',
            f'Incorrect API key provided: {OPENAI_KEY}',
            f'chave {NVIDIA_KEY} recusada',
            f'cabeçalho Authorization: Token {DRF_TOKEN}',
            f'client_secret={MP_TOKEN}',
            f'graph.facebook.com/v26.0/me?fields=id&access_token={META_TOKEN}',
            f'hub.verify_token={DRF_TOKEN}',
            f'x-api-key: {DRF_TOKEN}',
        ]
        for texto in casos:
            with self.subTest(texto=texto[:40]):
                saida = redact_secrets(texto)
                for segredo in TODOS:
                    self.assertNotIn(segredo, saida)
                self.assertIn('[REDACTED]', saida)

    def test_tira_senha_da_url_de_conexao_e_mantem_o_host(self):
        saida = redact_secrets('could not connect: postgres://pastita:s3nh4F0rte@pgbouncer:6432/db')
        self.assertNotIn('s3nh4F0rte', saida)
        self.assertIn('pgbouncer:6432', saida)

    def test_nao_estraga_log_que_nao_tem_segredo(self):
        """Log de diagnóstico precisa continuar legível."""
        for texto in [
            'Pedido CE-2608113992 pago em 12.5s',
            'max_tokens: 1024, prompt_tokens=88, total_tokens=120',
            'store=ce-saladas order=7f9a8412-0000-4000-8000-1234567890ab',
            'GET https://api.mercadopago.com/v1/payments/123 -> 404',
            'Token inválido',
            'Falha ao enviar para 5563999998888',
            'risk-assessment concluído; task-queue=whatsapp',
        ]:
            with self.subTest(texto=texto):
                self.assertEqual(redact_secrets(texto), texto)

    def test_texto_enorme_nao_trava_o_log(self):
        for texto in ['a' * 500_000, 'token=' * 80_000, 'Bearer ' * 70_000, '://x:' * 100_000]:
            inicio = time.monotonic()
            redact_secrets(texto)
            self.assertLess(time.monotonic() - inicio, 1.0, texto[:10])


class JsonFormatterTest(TestCase):
    def test_mensagem(self):
        saida = _formata(lambda log: log.error('falhou: %s', f'access_token={MP_TOKEN}'))
        self.assertNotIn(MP_TOKEN, saida)
        self.assertEqual(json.loads(saida)['level'], 'ERROR')

    def test_traceback_do_logger_exception(self):
        """O caminho que os PRs #390 e #392 não fechavam."""
        def chamada(log):
            try:
                raise RuntimeError(f'401 Authorization: Bearer {MP_TOKEN}')
            except RuntimeError:
                log.exception('Erro ao criar pagamento')

        saida = _formata(chamada)
        self.assertNotIn(MP_TOKEN, saida)
        dados = json.loads(saida)
        self.assertEqual(dados['message'], 'Erro ao criar pagamento')
        self.assertIn('RuntimeError', dados['exception'])

    def test_extra_por_nome_de_campo_aninhado_e_objeto(self):
        class Resposta:
            def __str__(self):
                return f'<Resposta Bearer {MP_TOKEN}>'

        saida = _formata(lambda log: log.warning('x', extra={
            'password': 'abc',
            'payload': {'api_key': 'curta', 'lista': [f'token={DRF_TOKEN}'], 'ok': 1},
            'resposta': Resposta(),
        }))
        self.assertNotIn(MP_TOKEN, saida)
        self.assertNotIn(DRF_TOKEN, saida)
        extra = json.loads(saida)['extra']
        self.assertEqual(extra['password'], '[REDACTED]')
        self.assertEqual(extra['payload']['api_key'], '[REDACTED]')
        self.assertEqual(extra['payload']['ok'], 1)


class SentryTest(TestCase):
    """Evento completo, do logger ao envelope que seria enviado ao GlitchTip."""

    def _envelope_do_evento(self, acao):
        enviados = []

        class TransporteFalso(Transport):
            def capture_envelope(self, envelope: Envelope):
                enviados.append(envelope.serialize().decode('utf-8', 'replace'))

            def flush(self, timeout, callback=None):
                pass

        client = sentry_sdk.Client(
            dsn='https://chave@exemplo.invalid/1',
            transport=TransporteFalso,
            before_send=scrub_sentry_event,
            default_integrations=False,
            integrations=[LoggingIntegration(event_level=logging.ERROR)],
        )
        with sentry_sdk.new_scope() as scope:
            scope.set_client(client)
            acao()
        client.flush()
        self.assertTrue(enviados, 'nenhum evento chegou ao transporte')
        return '\n'.join(enviados)

    def test_excecao_capturada(self):
        def acao():
            try:
                raise RuntimeError(f'recusado access_token={MP_TOKEN}')
            except RuntimeError as exc:
                sentry_sdk.capture_exception(exc)

        saida = self._envelope_do_evento(acao)
        self.assertNotIn(MP_TOKEN, saida)
        self.assertIn('RuntimeError', saida)

    def test_erro_vindo_do_logger(self):
        logger = logging.getLogger('teste.sentry.redacao')
        saida = self._envelope_do_evento(
            lambda: logger.error('falhou com Bearer %s', MP_TOKEN)
        )
        self.assertNotIn(MP_TOKEN, saida)
        self.assertIn('falhou com', saida)

    def test_variavel_local_do_traceback(self):
        def acao():
            texto_da_resposta = f'corpo com token={DRF_TOKEN}'
            try:
                raise RuntimeError('falha genérica')
            except RuntimeError as exc:
                sentry_sdk.capture_exception(exc)
            return texto_da_resposta

        self.assertNotIn(DRF_TOKEN, self._envelope_do_evento(acao))

    def test_se_a_limpeza_falhar_o_evento_nao_sai(self):
        """Na dúvida, não envia: o erro ainda fica no log do container."""
        class Explosivo(dict):
            def items(self):
                raise RuntimeError('quebrou')

        self.assertIsNone(scrub_sentry_event({'extra': Explosivo(a=MP_TOKEN)}, {}))
