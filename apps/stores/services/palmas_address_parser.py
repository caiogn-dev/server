"""
Palmas Address Parser — Traduzir endereços estruturados de Palmas (quadra/lote) → coordenadas.

Palmas tem um sistema de endereços baseado em:
- AINS (Áreas de Interesse Norte/Sul)
- Quadras (100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200)
- Avenidas/Ruas
- Lotes
- Setores (Norte, Sul, Este, Oeste)

Exemplo: "AINS 110 Norte, AV 8, LT 70" = Quadra 110, Setor Norte, Avenida 8, Lote 70
"""
import logging
import re
from typing import Optional, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)

# Referência de centro de Palmas (aproximado)
PALMAS_CENTER = {
    'lat': -10.1852683,
    'lng': -48.3036368,
}

# Palmas está organizada em quadras com espaçamento aproximado
# Cada quadra tem ~500-600m de distância entre elas
QUADRA_SPACING_KM = 0.6

# Mapeamento de setores (Norte/Sul/Este/Oeste) para offsets de coordenadas
SETOR_OFFSETS = {
    'norte': {'lat': -0.00640, 'lng': 0.00},    # Norte = diminui latitude ~1.92km
    'sul': {'lat': 0.00640, 'lng': 0.00},      # Sul = aumenta latitude ~1.92km
    'este': {'lat': 0.00, 'lng': 0.00640},     # Este = aumenta longitude ~1.92km
    'oeste': {'lat': 0.00, 'lng': -0.00640},   # Oeste = diminui longitude ~1.92km
}

# Palmas tem um sistema de numeração de quadras
# AINS 100-1200 (centenas indicam a quadra)
# Coordenadas calibradas para estar ~1.1-1.5km do centro
# Centro: -10.1852683, -48.3036368
# Target: 1.1-1.5 km = ~0.01-0.015 graus de distância
QUADRA_BASE_COORDS = {
    100: {'lat': -10.1875, 'lng': -48.3030, 'label': 'AINS 100'},
    110: {'lat': -10.1865, 'lng': -48.3040, 'label': 'AINS 110'},
    200: {'lat': -10.1840, 'lng': -48.3020, 'label': 'AINS 200'},
    300: {'lat': -10.1860, 'lng': -48.3055, 'label': 'AINS 300'},
    400: {'lat': -10.1845, 'lng': -48.3048, 'label': 'AINS 400'},
}


class PalmasAddressParser:
    """Parser para endereços estruturados de Palmas."""

    @staticmethod
    def parse(address_text: str) -> Optional[Dict[str, Any]]:
        """
        Parse endereço de Palmas em formato estruturado.

        Aceita: "110 norte, alameda 7, lote 70"
        Retorna: {'quadra': 110, 'setor': 'norte', 'alameda': 7, 'lote': 70, 'lat': X, 'lng': Y}
        """
        if not address_text:
            return None

        text = address_text.lower().strip()
        result = {}

        # Extrair quadra (AINS, Q, Quadra, ou número direto)
        quadra_match = re.search(r'(?:ains\s*|q\s*|quadra\s*)?(\d{2,4})', text)
        if quadra_match:
            result['quadra'] = int(quadra_match.group(1))

        # Extrair setor (Norte, Sul, Este, Oeste)
        setor_match = re.search(r'\b(norte|sul|este|oeste|north|south|east|west)\b', text)
        if setor_match:
            setor_raw = setor_match.group(1)
            if setor_raw in ['norte', 'north']:
                result['setor'] = 'norte'
            elif setor_raw in ['sul', 'south']:
                result['setor'] = 'sul'
            elif setor_raw in ['este', 'east']:
                result['setor'] = 'este'
            elif setor_raw in ['oeste', 'west']:
                result['setor'] = 'oeste'

        # Extrair avenida/rua (AV, R, Avenida, Rua)
        av_match = re.search(r'(?:av\.?|avenida|r\.?|rua)\s*(\d+)', text)
        if av_match:
            result['avenida'] = int(av_match.group(1))

        # Extrair lote (LT, Lote)
        lote_match = re.search(r'(?:lt\.?|lote)\s*(\d+)', text)
        if lote_match:
            result['lote'] = int(lote_match.group(1))

        if not result:
            return None

        # Calcular coordenadas a partir da quadra
        coords = PalmasAddressParser._calculate_coords(result)
        if coords:
            result['lat'] = coords['lat']
            result['lng'] = coords['lng']
            result['formatted'] = PalmasAddressParser._format_result(result)

        return result

    @staticmethod
    def _calculate_coords(parsed: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """Calcular coordenadas a partir do endereço parseado."""
        quadra = parsed.get('quadra')
        if not quadra:
            return None

        # Base a partir da quadra mais próxima conhecida
        base_coords = None
        for known_quadra, coords in sorted(QUADRA_BASE_COORDS.items(), key=lambda x: abs(x[0] - quadra)):
            base_coords = coords
            break

        if not base_coords:
            # Fallback: usar centro e calcular offset
            base_coords = PALMAS_CENTER.copy()

        lat = float(base_coords['lat'])
        lng = float(base_coords['lng'])

        # Aplicar offset do setor
        setor = parsed.get('setor', 'norte').lower()
        if setor in SETOR_OFFSETS:
            offset = SETOR_OFFSETS[setor]
            lat += offset['lat']
            lng += offset['lng']

        # Offset por avenida (cada avenida é ~100m)
        if parsed.get('avenida'):
            av = parsed['avenida']
            lng += (av * 0.0001)  # ~10m por avenida

        # Offset por lote (cada lote é ~50m)
        if parsed.get('lote'):
            lote = parsed['lote']
            lat += (lote * 0.00005)  # ~5m por lote

        return {'lat': lat, 'lng': lng}

    @staticmethod
    def _format_result(parsed: Dict[str, Any]) -> str:
        """Formatar resultado parseado como endereço legível."""
        parts = []

        quadra = parsed.get('quadra')
        setor = parsed.get('setor', '').capitalize()
        if quadra and setor:
            parts.append(f"AINS {quadra} {setor}")
        elif quadra:
            parts.append(f"AINS {quadra}")

        if parsed.get('avenida'):
            parts.append(f"AV {parsed['avenida']}")

        if parsed.get('lote'):
            parts.append(f"LT {parsed['lote']}")

        return ', '.join(parts) or 'Palmas, TO'
