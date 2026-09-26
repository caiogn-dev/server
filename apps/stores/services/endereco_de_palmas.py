"""Endereço de Palmas digitado por gente: quadra, setor, alameda e lote.

Palmas é endereçada por quadra + setor ("307 Norte", "ARSE 72", "112 Sul"),
não por nome de rua. O Google só acerta quando a quadra vem explícita: em
25/09 "Na 307 norte Al 19 lote 53 sala 03" virou *Alameda 19, 53 — Plano
Diretor Sul* (14,1 km) em vez de *Q. 307 Norte, Arno* (5 km).

Duas peças, as duas puras:
- `consulta_para_geocodificar`: monta "Quadra 307 Norte, Alameda 19, 53,
  Palmas - TO" quando o texto tem quadra + setor + rua + número; senão devolve
  o texto como veio.
- `resultado_bate_com_o_setor`: Norte que volta como Sul é resultado errado,
  não endereço.

O `PalmasAddressParser` antigo calcula coordenadas por grade — não serve para
taxa de entrega (307 Norte caía a 500 m da loja). Aqui só se monta a consulta;
quem geocodifica continua sendo o provedor.
"""
from __future__ import annotations

import re

#: Siglas dos setores de Palmas: ARSE/ACSU/ARSO = Sul; ARNE/ARNO/ACNO = Norte.
_SIGLA_SUL = ('arse', 'acsu', 'arso', 'acso', 'aase', 'aaso')
_SIGLA_NORTE = ('arne', 'arno', 'acno', 'acne', 'aane', 'aano')

_RE_QUADRA = re.compile(
    r'(?:\b(?P<sigla>q\.?|quadra|qd\.?|ains|arse|arne|arno|arso|acsu|acno|acso|acne|aase|aaso|aane|aano)\s*)?'
    r'\b(\d{2,4})\s*(?:-\s*)?(norte|sul|n|s)?\b',
    re.IGNORECASE,
)
_RE_RUA = re.compile(r'\b(alameda|al\.?|avenida|av\.?|rua|r\.?|ns|lo)\s*(\d+)\b', re.IGNORECASE)
_RE_NUMERO = re.compile(r'\b(?:lote|lt\.?|lt|n[º°o]?\.?|numero|número|casa|nr\.?)\s*(\d+)\b', re.IGNORECASE)

_TIPO_DE_RUA = {'al': 'Alameda', 'alameda': 'Alameda', 'av': 'Avenida', 'avenida': 'Avenida',
                'rua': 'Rua', 'r': 'Rua', 'ns': 'Avenida NS', 'lo': 'Avenida LO'}


def analisar(texto: str) -> dict:
    """{'quadra', 'setor', 'rua', 'numero'} — só o que dá para afirmar."""
    bruto = str(texto or '')
    baixo = bruto.lower()
    dado: dict = {}

    m = _RE_QUADRA.search(bruto)
    if m:
        dado['quadra'] = int(m.group(2))
        setor = (m.group(3) or '').lower()
        # A sigla faz parte do casamento (m.start() cai nela), então é lida
        # do próprio grupo — "ARSE 72" é Sul mesmo sem a palavra.
        sigla = (m.group('sigla') or '').lower().rstrip('.')
        if setor in ('norte', 'n'):
            dado['setor'] = 'Norte'
        elif setor in ('sul', 's'):
            dado['setor'] = 'Sul'
        elif sigla in _SIGLA_SUL:
            dado['setor'] = 'Sul'
        elif sigla in _SIGLA_NORTE:
            dado['setor'] = 'Norte'
        elif re.search(r'\bnorte\b', baixo):
            dado['setor'] = 'Norte'
        elif re.search(r'\bsul\b', baixo):
            dado['setor'] = 'Sul'

    m = _RE_RUA.search(bruto)
    if m:
        tipo = m.group(1).lower().rstrip('.')
        dado['rua'] = f"{_TIPO_DE_RUA.get(tipo, tipo.title())} {int(m.group(2))}"

    m = _RE_NUMERO.search(bruto)
    if m:
        dado['numero'] = int(m.group(1))
    return dado


def consulta_para_geocodificar(texto: str) -> str:
    """A consulta que o geocodificador entende — ou o texto como veio."""
    dado = analisar(texto)
    if not all(k in dado for k in ('quadra', 'setor', 'rua', 'numero')):
        return str(texto or '')
    return f"Quadra {dado['quadra']} {dado['setor']}, {dado['rua']}, {dado['numero']}, Palmas - TO"


def setor_digitado(texto: str) -> str:
    """'307 Norte' — para dizer ao cliente o que foi lido."""
    dado = analisar(texto)
    if 'quadra' in dado and 'setor' in dado:
        return f"{dado['quadra']} {dado['setor']}"
    return str(texto or '')


def resultado_bate_com_o_setor(texto: str, geo: dict | None) -> bool:
    """Falso quando o cliente escreveu um setor e o resultado é do outro."""
    setor = analisar(texto).get('setor')
    if not setor or not geo:
        return True
    achado = str(geo.get('formatted_address') or geo.get('display_name') or '').lower()
    esperado, oposto = ('norte', 'sul') if setor == 'Norte' else ('sul', 'norte')
    if re.search(rf'\b{esperado}\b', achado):
        return True
    return not re.search(rf'\b{oposto}\b', achado)
