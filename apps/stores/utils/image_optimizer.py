"""
Image optimization utilities for product and category images.
Converts to WebP, redimensiona com aspect ratio preservation.
"""
from pathlib import Path
from PIL import Image
import logging

logger = logging.getLogger(__name__)


class ImageOptimizer:
    """
    Otimiza imagens para WebP com redimensionamento automático.
    """

    DEFAULT_MAX_WIDTH = 600
    DEFAULT_MAX_HEIGHT = 600

    def optimize(self, image_path, max_width=None, max_height=None):
        """
        Otimiza uma imagem: redimensiona, converte para WebP, comprime.

        Args:
            image_path (str): Caminho completo da imagem
            max_width (int): Largura máxima em pixels (default: 600)
            max_height (int): Altura máxima em pixels (default: 600)

        Returns:
            str: Caminho da imagem otimizada (.webp) ou None se falhar
        """
        max_width = max_width or self.DEFAULT_MAX_WIDTH
        max_height = max_height or self.DEFAULT_MAX_HEIGHT

        image_path = Path(image_path)

        # Validar arquivo
        if not image_path.exists():
            logger.warning(f"Imagem não encontrada: {image_path}")
            return None

        try:
            # Abrir imagem original
            img = Image.open(image_path)

            # Converter RGBA -> RGB se necessário (WebP pode gerar problemas com RGBA)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Criar fundo branco
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = bg

            # Redimensionar mantendo aspect ratio
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            # Gerar caminho de saída (.webp)
            output_path = image_path.parent / f"{image_path.stem}.webp"

            # Salvar como WebP (otimizado)
            img.save(output_path, 'WEBP', quality=80, method=6)

            logger.info(f"Imagem otimizada: {image_path} → {output_path} ({img.width}x{img.height})")

            return str(output_path)

        except Exception as e:
            logger.error(f"Erro ao otimizar {image_path}: {e}")
            return None
