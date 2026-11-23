"""O bot ouve áudio: a voz do cliente vira texto (Whisper na NVIDIA) e segue o
caminho de qualquer mensagem escrita.

Até 23/11 o áudio entrava no inbox com `text_body` vazio e o pipeline o
ignorava de propósito ("sem transcrição, silêncio é melhor que 'não entendi'").
Quem pedia por áudio ficava sem resposta até um atendente ouvir.
"""
import sys
import types
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.whatsapp.services import transcricao_de_audio
from apps.whatsapp.services.webhook_service import WebhookService


def _riva_falso(transcricoes=None, erro=None):
    """Módulo `riva.client` mínimo: o suficiente para o serviço chamar."""
    chamadas = {}

    class Auth:
        def __init__(self, **kw):
            chamadas['auth'] = kw

    class RecognitionConfig:
        def __init__(self, **kw):
            chamadas['config'] = kw

    class ASRService:
        def __init__(self, auth):
            pass

        def offline_recognize(self, dados, config, future=False):
            chamadas['bytes'] = dados
            chamadas['future'] = future
            alt = lambda t: types.SimpleNamespace(alternatives=[types.SimpleNamespace(transcript=t)])
            resposta = types.SimpleNamespace(results=[alt(t) for t in (transcricoes or [])])

            def result(timeout=None):
                chamadas['timeout'] = timeout
                if erro:
                    raise erro
                return resposta
            return types.SimpleNamespace(result=result)

    client = types.SimpleNamespace(Auth=Auth, RecognitionConfig=RecognitionConfig, ASRService=ASRService)
    riva = types.ModuleType('riva')
    riva.client = client
    return {'riva': riva, 'riva.client': client}, chamadas


@override_settings(NVIDIA_API_KEY='chave-teste')
class TranscreverTest(SimpleTestCase):
    def test_junta_os_trechos_em_um_texto(self):
        modulos, chamadas = _riva_falso([' Quero uma salada. ', 'Sem cebola'])
        with mock.patch.dict(sys.modules, modulos):
            texto = transcricao_de_audio.transcrever(b'ogg')
        self.assertEqual(texto, 'Quero uma salada. Sem cebola')
        self.assertEqual(chamadas['bytes'], b'ogg')
        self.assertEqual(chamadas['config']['language_code'], 'pt')
        self.assertTrue(chamadas['future'])
        self.assertEqual(chamadas['timeout'], transcricao_de_audio.LIMITE_S)
        metadata = dict(chamadas['auth']['metadata_args'])
        self.assertEqual(metadata['function-id'], transcricao_de_audio.WHISPER_NA_NVIDIA)
        self.assertEqual(metadata['authorization'], 'Bearer chave-teste')

    def test_falha_da_nvidia_vira_texto_vazio(self):
        modulos, _ = _riva_falso(erro=RuntimeError('UNAVAILABLE'))
        with mock.patch.dict(sys.modules, modulos):
            self.assertEqual(transcricao_de_audio.transcrever(b'ogg'), '')

    def test_sem_bytes_nem_chama(self):
        modulos, chamadas = _riva_falso(['x'])
        with mock.patch.dict(sys.modules, modulos):
            self.assertEqual(transcricao_de_audio.transcrever(b''), '')
        self.assertNotIn('bytes', chamadas)

    @override_settings(NVIDIA_API_KEY='')
    def test_sem_chave_nao_transcreve(self):
        modulos, chamadas = _riva_falso(['x'])
        with mock.patch.dict(sys.modules, modulos):
            self.assertEqual(transcricao_de_audio.transcrever(b'ogg'), '')
        self.assertNotIn('bytes', chamadas)

    def test_sem_biblioteca_nao_quebra(self):
        with mock.patch.dict(sys.modules, {'riva': None, 'riva.client': None}):
            self.assertEqual(transcricao_de_audio.transcrever(b'ogg'), '')


class AudioChegaComTextoTest(SimpleTestCase):
    def _montar(self, tipo, dados):
        service = WebhookService.__new__(WebhookService)
        event = types.SimpleNamespace(account=object())
        return service._build_message_content(event, {tipo: dados}, tipo, '5563999999999')

    def test_audio_vira_texto_da_mensagem(self):
        with mock.patch.object(WebhookService, '_baixar_midia', return_value=('https://m/a.ogg', 'sha', b'ogg')), \
             mock.patch.object(transcricao_de_audio, 'transcrever', return_value='Quero duas saladas') as tr:
            text_body, content, media_id, media_url, mime, sha = self._montar(
                'audio', {'id': 'm1', 'mime_type': 'audio/ogg; codecs=opus', 'voice': True})
        tr.assert_called_once_with(b'ogg')
        self.assertEqual(text_body, 'Quero duas saladas')
        self.assertEqual(content['audio']['transcricao'], 'Quero duas saladas')
        self.assertEqual((media_id, media_url, sha), ('m1', 'https://m/a.ogg', 'sha'))

    def test_audio_sem_transcricao_fica_sem_texto(self):
        with mock.patch.object(WebhookService, '_baixar_midia', return_value=('https://m/a.ogg', 'sha', b'ogg')), \
             mock.patch.object(transcricao_de_audio, 'transcrever', return_value=''):
            text_body, content, *_ = self._montar('audio', {'id': 'm1', 'mime_type': 'audio/ogg'})
        self.assertEqual(text_body, '')
        self.assertNotIn('transcricao', content['audio'])

    def test_imagem_nao_passa_pela_transcricao(self):
        with mock.patch.object(WebhookService, '_baixar_midia', return_value=('https://m/i.jpg', 'sha', b'jpg')), \
             mock.patch.object(transcricao_de_audio, 'transcrever') as tr:
            text_body, *_ = self._montar('image', {'id': 'i1', 'mime_type': 'image/jpeg', 'caption': 'olha'})
        tr.assert_not_called()
        self.assertEqual(text_body, 'olha')


class BotRespondeAudioTest(SimpleTestCase):
    def _msg(self, tipo, texto):
        return types.SimpleNamespace(message_type=tipo, text_body=texto)

    def test_audio_transcrito_pede_resposta(self):
        self.assertFalse(WebhookService._nao_pede_resposta(self._msg('audio', 'Quero uma salada')))

    def test_audio_sem_transcricao_continua_em_silencio(self):
        self.assertTrue(WebhookService._nao_pede_resposta(self._msg('audio', '')))
        self.assertTrue(WebhookService._nao_pede_resposta(self._msg('audio', '   ')))

    def test_reacao_continua_sem_resposta(self):
        self.assertTrue(WebhookService._nao_pede_resposta(self._msg('reaction', '❤️')))

    def test_texto_pede_resposta(self):
        self.assertFalse(WebhookService._nao_pede_resposta(self._msg('text', 'oi')))

    def test_audio_entra_na_rajada_com_o_texto(self):
        self.assertIn('audio', WebhookService.TIPOS_DA_RAJADA)
        self.assertIn('text', WebhookService.TIPOS_DA_RAJADA)
