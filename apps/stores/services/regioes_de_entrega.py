"""Regiões de entrega com regras próprias (zonas fixas em `metadata['fixed_price_zones']`).

Caso de origem (06/10, Agrião): tudo sai de Palmas; Porto Nacional (R$ 25) e
Paraíso do Tocantins (R$ 30) recebem no DIA SEGUINTE (domingo não sai), só com
pagamento antecipado e só com as categorias que o lojista liberar.

Campos novos da zona (todos opcionais — zona sem eles se comporta como antes):
    categorias               ids de categoria permitidos ([] = todas)
    pedido_minimo            subtotal mínimo
    entrega_dia_seguinte     agenda para o próximo dia de entrega
    dias_sem_entrega         weekday (0=segunda … 6=domingo) em que não sai
    so_pagamento_antecipado  recusa dinheiro/maquininha na entrega

Uma regra, um lugar: a cotação (vitrine), o checkout e o bot leem daqui.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from apps.stores.formas_de_pagamento import PAGOS_NA_ENTREGA


class RegiaoRecusou(ValueError):
    """O pedido não cabe nas regras da região. A mensagem vai para o cliente."""


def _reais(v: Decimal) -> str:
    return f"R$ {v:.2f}".replace('.', ',')


def _decimal(valor) -> Optional[Decimal]:
    if valor in (None, ''):
        return None
    try:
        d = Decimal(str(valor).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None
    return d if d > 0 else None


@dataclass
class RegrasDaRegiao:
    nome: str
    taxa: Decimal
    categorias: List[str] = field(default_factory=list)
    pedido_minimo: Optional[Decimal] = None
    entrega_dia_seguinte: bool = False
    dias_sem_entrega: List[int] = field(default_factory=list)
    so_pagamento_antecipado: bool = False

    @classmethod
    def da_zona(cls, zona: dict) -> 'RegrasDaRegiao':
        return cls(
            nome=str(zona.get('name') or 'Região'),
            taxa=_decimal(zona.get('fee')) or Decimal('0'),
            categorias=[str(c) for c in (zona.get('categorias') or []) if c],
            pedido_minimo=_decimal(zona.get('pedido_minimo')),
            entrega_dia_seguinte=bool(zona.get('entrega_dia_seguinte')),
            dias_sem_entrega=[int(d) for d in (zona.get('dias_sem_entrega') or []) if str(d).isdigit() and 0 <= int(d) <= 6],
            so_pagamento_antecipado=bool(zona.get('so_pagamento_antecipado')),
        )

    @property
    def tem_regras(self) -> bool:
        return bool(self.categorias or self.pedido_minimo or self.entrega_dia_seguinte or self.so_pagamento_antecipado)

    def data_de_entrega(self, agora_local: datetime) -> Optional[date]:
        """Próximo dia de entrega a partir de amanhã, pulando os dias sem entrega."""
        if not self.entrega_dia_seguinte:
            return None
        dia = agora_local.date() + timedelta(days=1)
        for _ in range(7):
            if dia.weekday() not in self.dias_sem_entrega:
                return dia
            dia += timedelta(days=1)
        return None  # todos os dias bloqueados: configuração sem saída

    def erros(self, itens: Iterable[Tuple[str, Optional[str]]], subtotal: Decimal, forma_de_pagamento: str) -> List[str]:
        """`itens` = (nome do produto, id da categoria). Vazio = pedido cabe na região."""
        erros = []
        if self.categorias:
            permitidas = set(self.categorias)
            fora = sorted({nome for nome, categoria in itens if str(categoria or '') not in permitidas})
            if fora:
                erros.append(f"Para {self.nome} não entregamos: {', '.join(fora)}.")
        if self.pedido_minimo and Decimal(str(subtotal)) < self.pedido_minimo:
            erros.append(f"Pedido mínimo para {self.nome}: {_reais(self.pedido_minimo)}.")
        if self.so_pagamento_antecipado and forma_de_pagamento in PAGOS_NA_ENTREGA:
            erros.append(f"Para {self.nome} o pagamento é antecipado (PIX ou cartão online).")
        return erros

    def para_api(self, agora_local: Optional[datetime] = None) -> dict:
        entrega = self.data_de_entrega(agora_local) if agora_local else None
        return {
            'nome': self.nome,
            'taxa': str(self.taxa),
            'categorias': self.categorias,
            'pedido_minimo': str(self.pedido_minimo) if self.pedido_minimo else None,
            'entrega_dia_seguinte': self.entrega_dia_seguinte,
            'data_de_entrega': entrega.isoformat() if entrega else None,
            'so_pagamento_antecipado': self.so_pagamento_antecipado,
        }


def agora_na_loja(store) -> datetime:
    from django.utils import timezone
    try:
        fuso = ZoneInfo(getattr(store, 'timezone', '') or 'America/Araguaina')
    except Exception:
        fuso = ZoneInfo('America/Araguaina')
    return timezone.now().astimezone(fuso)


def zona_do_endereco(store, lat, lng, address_text: str = '') -> Optional[dict]:
    """A zona fixa que casa com o endereço — mesma regra da cotação (palavras-chave + reverse geocode)."""
    if not (store.metadata or {}).get('fixed_price_zones') or lat is None or lng is None:
        return None
    from apps.stores.services.geo import geo_service
    try:
        return geo_service._match_fixed_price_zone(store, float(lat), float(lng), address_text=address_text or '')
    except Exception:
        return None


def coordenadas_do_payload(payload: dict) -> Tuple[Optional[float], Optional[float], str]:
    """(lat, lng, texto do endereço) de um delivery payload em qualquer formato."""
    payload = payload or {}
    endereco = payload.get('address')
    texto = endereco if isinstance(endereco, str) else ''
    fontes = [payload]
    if isinstance(endereco, dict):
        fontes.append(endereco)
        texto = endereco.get('raw_address') or ', '.join(
            str(endereco.get(k) or '') for k in ('street', 'number', 'neighborhood', 'city', 'state') if endereco.get(k)
        )
    for fonte in fontes:
        lat = fonte.get('lat', fonte.get('latitude'))
        lng = fonte.get('lng', fonte.get('longitude'))
        if lat not in (None, '') and lng not in (None, ''):
            try:
                return float(lat), float(lng), texto
            except (TypeError, ValueError):
                pass
    return None, None, texto


def regiao_do_pedido(store, delivery_payload: dict) -> Optional[RegrasDaRegiao]:
    if (delivery_payload or {}).get('method') != 'delivery':
        return None
    lat, lng, texto = coordenadas_do_payload(delivery_payload)
    zona = zona_do_endereco(store, lat, lng, texto)
    if not zona or zona.get('surcharge_on_km'):
        return None
    return RegrasDaRegiao.da_zona(zona)
