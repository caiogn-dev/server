"""Orquestração dos vigias: teto, silêncio, idempotência, canal e pausa.

O envio ao WhatsApp é trocado por dublês nos pontos de costura do
`canal_do_dono` — o que se testa aqui é a decisão, não a Meta.
"""
from datetime import time, timedelta
from unittest.mock import patch

import pytest

from apps.stores.models import VigiaAviso, VigiaConfig, VigiaEnvio
from apps.stores.tests.factories import make_store
from apps.stores.tests.test_vigias_regras import local, pedido
from apps.stores.vigias import canal_do_dono, comandos, runner
from apps.stores.vigias.regras import Fato

SEXTA_8H = local(2026, 10, 16, 8, 5)
DONO = '5563999112233'


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def config(loja):
    return VigiaConfig.objects.create(store=loja, ativo=True, telefone=DONO)


def _fato(tipo, n, prioridade=5, grupo=None, intervalo=0):
    return Fato(tipo=tipo, chave=f'{tipo}:{n}', grupo=grupo or f'{tipo}:{n}', titulo=f'{tipo} {n}',
                texto=f'texto {tipo} {n}', prioridade=prioridade, intervalo_dias=intervalo)


class Canal:
    """Dublê: registra o que seria enviado."""

    def __init__(self, janela=True, modelo=True, falha=None):
        self.janela, self.modelo, self.falha = janela, modelo, falha
        self.textos, self.modelos = [], []

    def __enter__(self):
        self._p = [
            patch.object(canal_do_dono, 'janela_aberta', lambda conta, tel: self.janela),
            patch.object(canal_do_dono, 'modelo_aprovado', lambda conta: self.modelo),
            patch.object(canal_do_dono, '_conta_da_loja', lambda loja: object()),
            patch.object(canal_do_dono, '_enviar_texto', self._texto),
            patch.object(canal_do_dono, '_enviar_modelo', self._modelo),
        ]
        for p in self._p:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._p:
            p.stop()

    def _texto(self, conta, tel, texto):
        if self.falha:
            raise self.falha
        self.textos.append((tel, texto))
        return 'wamid.texto'

    def _modelo(self, conta, tel, loja_nome, linha):
        if self.falha:
            raise self.falha
        self.modelos.append((tel, loja_nome, linha))
        return 'wamid.modelo'


def _regras(*fatos):
    return patch.object(runner, 'REGRAS_DA_MANHA', (('x', lambda loja, agora: list(fatos)),))


class TestQuandoRoda:
    def test_desligado_nao_faz_nada(self, loja, config):
        config.ativo = False
        config.save()
        with Canal() as c, _regras(_fato('resumo', 1)):
            runner.tick(SEXTA_8H)
        assert not VigiaEnvio.objects.exists() and not c.textos

    def test_antes_da_hora_nao_roda(self, loja, config):
        with Canal() as c, _regras(_fato('resumo', 1)):
            runner.tick(SEXTA_8H.replace(hour=7, minute=50))
        assert not VigiaEnvio.objects.exists() and not c.textos

    def test_fim_de_semana_fora_dos_dias_nao_roda(self, loja, config):
        with Canal() as c, _regras(_fato('resumo', 1)):
            runner.tick(local(2026, 10, 17, 9, 0))  # sábado
        assert not c.textos

    def test_pausado_nao_roda(self, loja, config):
        config.pausado_em = SEXTA_8H
        config.save()
        with Canal() as c, _regras(_fato('resumo', 1)):
            runner.tick(SEXTA_8H)
        assert not c.textos

    def test_madrugada_nao_manda_atrasado(self, loja, config):
        """Servidor fora do ar até as 22h não manda o resumo da manhã de noite."""
        with Canal() as c, _regras(_fato('resumo', 1)):
            runner.tick(SEXTA_8H.replace(hour=22))
        assert not c.textos


class TestMensagem:
    def test_uma_mensagem_com_no_maximo_tres_itens_por_prioridade(self, loja, config):
        fatos = [_fato('a', 1, 2), _fato('b', 2, 10), _fato('c', 3, 7), _fato('d', 4, 9), _fato('e', 5, 1)]
        with Canal() as c, _regras(*fatos):
            runner.tick(SEXTA_8H)

        assert len(c.textos) == 1
        tel, texto = c.textos[0]
        assert tel == DONO
        assert texto.index('texto b 2') < texto.index('texto d 4') < texto.index('texto c 3')
        assert 'texto a 1' not in texto and '+2' in texto
        assert VigiaAviso.objects.filter(store=loja).count() == 5
        envio = VigiaEnvio.objects.get()
        assert envio.status == 'enviado' and envio.canal == 'texto' and envio.mensagem_id == 'wamid.texto'
        assert envio.avisos.count() == 5

    def test_rodar_duas_vezes_nao_repete(self, loja, config):
        with Canal() as c, _regras(_fato('resumo', 1)):
            runner.tick(SEXTA_8H)
            runner.tick(SEXTA_8H + timedelta(minutes=10))
        assert len(c.textos) == 1
        assert VigiaEnvio.objects.count() == 1

    def test_fato_ja_avisado_noutro_dia_nao_volta(self, loja, config):
        with Canal() as c, _regras(_fato('resumo', 1)):
            runner.tick(SEXTA_8H)
            runner.tick(SEXTA_8H + timedelta(days=3))  # segunda
        assert len(c.textos) == 1
        assert VigiaEnvio.objects.get(dia='2026-10-19').status == 'silencio'

    def test_intervalo_minimo_por_assunto(self, loja, config):
        primeiro = _fato('sabor_em_queda', 'w42', grupo='sabor_em_queda:almondega', intervalo=14)
        semana_seguinte = _fato('sabor_em_queda', 'w43', grupo='sabor_em_queda:almondega', intervalo=14)
        with Canal() as c:
            with _regras(primeiro):
                runner.tick(SEXTA_8H)
            with _regras(semana_seguinte):
                runner.tick(SEXTA_8H + timedelta(days=7))
        assert len(c.textos) == 1

    def test_sem_nada_a_dizer_fica_em_silencio(self, loja, config):
        with Canal() as c, _regras():
            runner.tick(SEXTA_8H)
        assert not c.textos
        assert VigiaEnvio.objects.get().status == 'silencio'

    def test_regra_que_quebra_nao_derruba_as_outras(self, loja, config):
        def quebra(loja, agora):
            raise RuntimeError('boom')
        regras = (('quebra', quebra), ('ok', lambda loja, agora: [_fato('ok', 1)]))
        with Canal() as c, patch.object(runner, 'REGRAS_DA_MANHA', regras):
            runner.tick(SEXTA_8H)
        assert 'texto ok 1' in c.textos[0][1]

    def test_tipo_desligado_nao_roda(self, loja, config):
        config.desligados = ['x']
        config.save()
        with Canal() as c, _regras(_fato('resumo', 1)):
            runner.tick(SEXTA_8H)
        assert not c.textos


class TestCanal:
    def test_fora_da_janela_vai_pelo_modelo_em_uma_linha(self, loja, config):
        with Canal(janela=False) as c, _regras(_fato('a', 1, 9), _fato('b', 2, 8)):
            runner.tick(SEXTA_8H)
        assert not c.textos
        tel, nome, linha = c.modelos[0]
        assert nome == 'Cê Saladas' and '\n' not in linha
        assert 'texto a 1' in linha and 'texto b 2' in linha
        assert VigiaEnvio.objects.get().canal == 'modelo'

    def test_sem_janela_e_sem_modelo_fica_no_painel_com_motivo(self, loja, config):
        with Canal(janela=False, modelo=False) as c, _regras(_fato('a', 1)):
            runner.tick(SEXTA_8H)
        envio = VigiaEnvio.objects.get()
        assert envio.status == 'so_painel' and 'modelo' in envio.erro
        assert VigiaAviso.objects.filter(envio=envio).exists()

    def test_sem_telefone_fica_no_painel(self, loja, config):
        config.telefone = ''
        config.save()
        with Canal() as c, _regras(_fato('a', 1)):
            runner.tick(SEXTA_8H)
        assert VigiaEnvio.objects.get().status == 'so_painel'

    def test_falha_da_meta_fica_registrada_e_nao_repete_no_dia(self, loja, config):
        with Canal(falha=RuntimeError('(#131042) payment issue')) as c, _regras(_fato('a', 1)):
            runner.tick(SEXTA_8H)
            runner.tick(SEXTA_8H + timedelta(minutes=10))
        envio = VigiaEnvio.objects.get()
        assert envio.status == 'falhou' and '131042' in envio.erro

    def test_texto_falha_e_cai_no_modelo(self, loja, config):
        canal = Canal()
        with canal, _regras(_fato('a', 1)):
            with patch.object(canal_do_dono, '_enviar_texto', side_effect=RuntimeError('131047')):
                runner.tick(SEXTA_8H)
        assert canal.modelos and VigiaEnvio.objects.get().canal == 'modelo'


class TestAlerta:
    def test_alerta_e_turno_separado_e_uma_vez_por_dia(self, loja, config):
        alerta = _fato('sem_pedido', 1, 9)
        with Canal() as c, _regras(), patch.object(runner, 'sem_pedido_hoje', lambda *a, **k: [alerta]):
            runner.tick(local(2026, 10, 16, 12, 40))
            runner.tick(local(2026, 10, 16, 13, 10))
        assert len(c.textos) == 1 and 'Alerta' in c.textos[0][1]
        assert set(VigiaEnvio.objects.values_list('turno', flat=True)) == {'manha', 'alerta'}

    def test_alerta_respeita_hora_configurada(self, loja, config):
        config.hora_alerta = time(13, 30)
        config.save()
        chamado = []
        with Canal(), _regras(), patch.object(runner, 'sem_pedido_hoje',
                                              lambda loja, agora, hora_alerta: chamado.append(hora_alerta) or []):
            runner.tick(local(2026, 10, 16, 12, 40))
        assert chamado == []
        assert not VigiaEnvio.objects.filter(turno='alerta').exists()


class TestPrevia:
    def test_previa_nao_grava_nem_envia(self, loja, config):
        with Canal() as c, _regras(_fato('a', 1)):
            fatos = runner.previa(loja, SEXTA_8H)
        assert [f.chave for f in fatos] == ['a:1']
        assert not VigiaAviso.objects.exists() and not VigiaEnvio.objects.exists() and not c.textos

    def test_previa_com_regras_reais(self, loja, config):
        pedido(loja, local(2026, 10, 15, 12), [('Queridinha', 2, 36.99, 14)])
        fatos = runner.previa(loja, SEXTA_8H)
        assert fatos[0].tipo == 'resumo'


class TestComandosDoDono:
    def test_parar_e_voltar_pelo_whatsapp(self, loja, config):
        resposta = comandos.responder(loja, '+55 (63) 99911-2233', 'Parar avisos.')
        config.refresh_from_db()
        assert config.pausado_em is not None and 'pausad' in resposta.lower()

        resposta = comandos.responder(loja, DONO, 'voltar avisos')
        config.refresh_from_db()
        assert config.pausado_em is None and 'volta' in resposta.lower()

    def test_outro_telefone_nao_mexe(self, loja, config):
        assert comandos.responder(loja, '5563988887777', 'parar avisos') is None
        config.refresh_from_db()
        assert config.pausado_em is None

    def test_frase_comum_nao_e_comando(self, loja, config):
        assert comandos.responder(loja, DONO, 'parar') is None
        assert comandos.responder(loja, DONO, 'quero parar de receber promoções') is None

    def test_loja_sem_vigia_ignora(self, loja):
        assert comandos.responder(loja, DONO, 'parar avisos') is None
