"""Foto do cardápio padronizada no envio — gira pelo EXIF, reduz e grava WebP.

13/10: 343 fotos somavam 187 MB (média 545 KB), 115 em PNG; nada era tratado
no upload. O recorte NÃO acontece aqui (cortaria o prato para sempre): a
proporção é decidida na vitrine, pela configuração `exibicao` da loja.
"""
import io
import logging
import os

from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

LADO_MAXIMO = 1280
QUALIDADE = 82


def normalizar_bytes(conteudo: bytes) -> bytes | None:
    """Imagem → WebP de no máximo LADO_MAXIMO. None = deixar como veio."""
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(conteudo))
        img.load()
    except Exception:
        return None
    # GIF animado perderia a animação; não é foto de prato.
    if getattr(img, 'is_animated', False):
        return None
    img = ImageOps.exif_transpose(img)
    tem_alfa = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
    img = img.convert('RGBA' if tem_alfa else 'RGB')
    img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    saida = io.BytesIO()
    img.save(saida, 'WEBP', quality=QUALIDADE, method=4)
    return saida.getvalue()


def normalizar_campo(campo) -> bool:
    """Troca o arquivo ainda não gravado do ImageField pela versão WebP."""
    if not campo or getattr(campo, '_committed', True):
        return False
    try:
        campo.file.seek(0)
        bruto = campo.file.read()
        campo.file.seek(0)
    except Exception:
        return False
    novo = normalizar_bytes(bruto)
    if novo is None:
        return False
    base = os.path.splitext(os.path.basename(campo.name or 'foto'))[0] or 'foto'
    campo.save(f'{base}.webp', ContentFile(novo), save=False)
    return True


# Modelo → campos de foto. A vitrine mostra todos estes.
CAMPOS_DE_FOTO = {
    'StoreProduct': ('main_image',),
    'StoreCombo': ('image',),
    'StoreProductVariant': ('image',),
    'StoreCategory': ('image',),
    'StoreProductType': ('image',),
}


def normalizar_instancia(instancia) -> None:
    for nome in CAMPOS_DE_FOTO.get(type(instancia).__name__, ()):
        try:
            normalizar_campo(getattr(instancia, nome, None))
        except Exception:
            # Foto original ainda serve; não derrubar o cadastro por isso.
            logger.exception('[foto] falhou ao padronizar %s.%s', type(instancia).__name__, nome)
