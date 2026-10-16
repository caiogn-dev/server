"""API dos vigias no painel.

    GET   /api/v1/stores/vigias/?store=<slug>              config + catálogo + estado do canal
    PATCH /api/v1/stores/vigias/?store=<slug>              liga/desliga, telefone, horários, dias, tipos, pausa
    GET   /api/v1/stores/vigias/avisos/?store=<slug>       histórico (o que foi avisado, por onde, se chegou)
    POST  /api/v1/stores/vigias/avisos/<id>/util/?store=   👍/👎 do dono
    GET   /api/v1/stores/vigias/previa/?store=<slug>       o que sairia agora, sem gravar nem enviar
    POST  /api/v1/stores/vigias/teste/?store=<slug>        manda a prévia ao telefone do dono, agora
    POST  /api/v1/stores/vigias/modelo/?store=<slug>       registra o modelo `vigia_do_dia` na Meta

Escopo pela fonte única (`accessible_store_ids`): loja de outro dono é 404.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import accessible_store_ids

from ..models import Store, VigiaAviso, VigiaConfig
from ..vigias import canal_do_dono, runner
from ..vigias.catalogo import CATALOGO, TIPOS
from ..vigias.regras import dia_curto


def _loja(request):
    param = request.query_params.get('store') or ''
    if not param:
        return None
    qs = Store.objects.filter(id__in=accessible_store_ids(request.user))
    try:
        uuid.UUID(param)
        return qs.filter(id=param).first()
    except (ValueError, AttributeError):
        return qs.filter(slug=param).first()


def _nao_achou():
    return Response({'error': 'Loja não encontrada'}, status=404)


def _telefone(valor) -> str | None:
    """Só dígitos, com DDI 55. None quando não dá para ser celular brasileiro."""
    digitos = ''.join(ch for ch in str(valor or '') if ch.isdigit())
    if not digitos:
        return ''
    if len(digitos) in (10, 11):
        digitos = '55' + digitos
    if not digitos.startswith('55') or len(digitos) not in (12, 13):
        return None
    return digitos


def _hora(valor):
    try:
        return datetime.strptime(str(valor).strip()[:5], '%H:%M').time()
    except (TypeError, ValueError):
        return None


def _config_json(config: VigiaConfig | None) -> dict:
    if config is None:
        config = VigiaConfig()
    return {
        'ativo': config.ativo,
        'pausado': config.pausado_em is not None,
        'pausado_em': config.pausado_em.isoformat() if config.pausado_em else None,
        'telefone': config.telefone,
        'hora_resumo': f'{config.hora_resumo:%H:%M}' if hasattr(config.hora_resumo, 'strftime') else str(config.hora_resumo)[:5],
        'hora_alerta': f'{config.hora_alerta:%H:%M}' if hasattr(config.hora_alerta, 'strftime') else str(config.hora_alerta)[:5],
        'dias': config.dias,
        'desligados': config.desligados or [],
    }


def _estado(loja, config) -> dict:
    conta = canal_do_dono._conta_da_loja(loja)
    ultimo = loja.vigia_envios.exclude(status='silencio').order_by('-criado_em').first()
    return {
        'config': _config_json(config),
        'catalogo': list(CATALOGO),
        'canal': {
            'whatsapp_conectado': conta is not None,
            'modelo': canal_do_dono.estado_do_modelo(conta),
            'conversa_aberta': bool(config and config.telefone and conta is not None
                                    and canal_do_dono.janela_aberta(conta, config.telefone)),
        },
        'ultimo_envio': _envio_json(ultimo) if ultimo else None,
    }


def _envio_json(envio) -> dict:
    return {'id': str(envio.id), 'dia': envio.dia.isoformat(), 'turno': envio.turno, 'status': envio.status,
            'canal': envio.canal, 'erro': envio.erro, 'criado_em': envio.criado_em.isoformat()}


def _aviso_json(aviso: VigiaAviso) -> dict:
    return {
        'id': str(aviso.id), 'tipo': aviso.tipo, 'titulo': aviso.titulo, 'texto': aviso.texto,
        'prioridade': aviso.prioridade, 'dados': aviso.dados, 'util': aviso.util,
        'criado_em': aviso.criado_em.isoformat(),
        'envio': _envio_json(aviso.envio) if aviso.envio_id else None,
    }


def _fato_json(fato) -> dict:
    return {'tipo': fato.tipo, 'titulo': fato.titulo, 'texto': fato.texto,
            'prioridade': fato.prioridade, 'dados': fato.dados}


class VigiasView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        loja = _loja(request)
        if not loja:
            return _nao_achou()
        return Response(_estado(loja, VigiaConfig.objects.filter(store=loja).first()))

    def patch(self, request):
        loja = _loja(request)
        if not loja:
            return _nao_achou()
        dados = request.data if isinstance(request.data, dict) else {}
        config, _ = VigiaConfig.objects.get_or_create(store=loja)
        erros = {}

        if 'ativo' in dados:
            config.ativo = bool(dados['ativo'])
        if 'telefone' in dados:
            telefone = _telefone(dados['telefone'])
            if telefone is None:
                erros['telefone'] = 'Use DDD + número, ex.: (63) 99999-0000.'
            else:
                config.telefone = telefone
        for campo in ('hora_resumo', 'hora_alerta'):
            if campo in dados:
                hora = _hora(dados[campo])
                if hora is None:
                    erros[campo] = 'Horário inválido.'
                else:
                    setattr(config, campo, hora)
        if 'dias' in dados:
            dias = dados['dias']
            if (not isinstance(dias, list) or not all(isinstance(d, int) and 0 <= d <= 6 for d in dias)):
                erros['dias'] = 'Dias inválidos.'
            else:
                config.dias = sorted(set(dias))
        if 'desligados' in dados:
            desligados = dados['desligados']
            if not isinstance(desligados, list) or not set(desligados) <= TIPOS:
                erros['desligados'] = 'Vigia desconhecido.'
            else:
                config.desligados = sorted(set(desligados))
        if 'pausado' in dados:
            config.pausado_em = timezone.now() if dados['pausado'] else None

        if config.ativo and not config.dias:
            erros['dias'] = 'Escolha pelo menos um dia.'
        if erros:
            return Response({'error': 'Confira os campos.', 'campos': erros}, status=400)
        config.save()
        return Response(_estado(loja, config))


class VigiaAvisosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        loja = _loja(request)
        if not loja:
            return _nao_achou()
        try:
            limite = max(1, min(int(request.query_params.get('limite', 30)), 100))
        except (TypeError, ValueError):
            limite = 30
        avisos = VigiaAviso.objects.filter(store=loja).select_related('envio').order_by('-criado_em', '-prioridade')
        tipo = request.query_params.get('tipo')
        if tipo:
            avisos = avisos.filter(tipo=tipo)
        return Response({'resultados': [_aviso_json(a) for a in avisos[:limite]]})


class VigiaAvisoUtilView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, aviso_id):
        loja = _loja(request)
        if not loja:
            return _nao_achou()
        aviso = VigiaAviso.objects.filter(store=loja, id=aviso_id).first()
        if not aviso:
            return Response({'error': 'Aviso não encontrado'}, status=404)
        util = request.data.get('util') if isinstance(request.data, dict) else None
        if util not in (True, False, None):
            return Response({'error': 'util deve ser true, false ou null'}, status=400)
        aviso.util = util
        aviso.save(update_fields=['util'])
        return Response(_aviso_json(aviso))


class VigiaPreviaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        loja = _loja(request)
        if not loja:
            return _nao_achou()
        fatos = runner.previa(loja)
        principais = fatos[:runner.MAXIMO_DE_ITENS]
        texto, _ = runner.compor(loja, 'manha', timezone.localdate(), principais,
                                 max(0, len(fatos) - runner.MAXIMO_DE_ITENS))
        return Response({'fatos': [_fato_json(f) for f in fatos], 'mensagem': texto if fatos else '',
                         'dia': dia_curto(timezone.localdate())})


class VigiaTesteView(APIView):
    """Manda a prévia ao telefone do dono agora. Não grava aviso nem conta como turno."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        loja = _loja(request)
        if not loja:
            return _nao_achou()
        config = VigiaConfig.objects.filter(store=loja).first()
        if config is None or not config.telefone:
            return Response({'error': 'Cadastre o telefone que recebe os avisos.'}, status=400)
        fatos = runner.previa(loja)[:runner.MAXIMO_DE_ITENS]
        if not fatos:
            from ..vigias.regras import Fato
            fatos = [Fato(tipo='teste', chave='teste', grupo='teste', titulo='Teste',
                          texto='Tudo certo por aqui: os avisos vão chegar neste número.')]
        texto, linha = runner.compor(loja, 'manha', timezone.localdate(), fatos, 0)
        entrega = canal_do_dono.entregar(loja, config.telefone, '🧪 *Teste*\n' + texto, linha)
        status = 200 if entrega.status == 'enviado' else 409
        return Response({'status': entrega.status, 'canal': entrega.canal, 'erro': entrega.erro}, status=status)


class VigiaModeloView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        loja = _loja(request)
        if not loja:
            return _nao_achou()
        conta = canal_do_dono._conta_da_loja(loja)
        if conta is None:
            return Response({'error': 'Conecte o WhatsApp da loja primeiro.'}, status=400)
        try:
            canal_do_dono.criar_modelo(conta)
        except Exception as exc:  # noqa: BLE001 — a Meta explica o motivo na mensagem
            return Response({'error': f'A Meta recusou: {str(exc)[:200]}'}, status=502)
        return Response({'modelo': canal_do_dono.estado_do_modelo(conta)})
