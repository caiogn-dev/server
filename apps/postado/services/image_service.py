import io
import base64
import logging
from typing import Optional
import openai
from PIL import Image, ImageDraw
from apps.postado.models import PostadoPost, PostadoClient

logger = logging.getLogger(__name__)

FEED_SIZE = (1080, 1080)
STORIES_SIZE = (1080, 1920)

NICHE_IMAGE_STYLE = {
    'restaurant': 'food photography, restaurant, warm lighting, appetizing, high-end cuisine, professional',
    'salon': 'beauty salon, hair care, elegant interior, soft lighting, luxury beauty treatment, professional',
    'store': 'retail store, product display, modern interior, clean background, lifestyle photography, professional',
}


class ImageService:
    def generate_base_image(self, post: PostadoPost, caption: str) -> Image.Image:
        client_obj: PostadoClient = post.pack.client
        style = NICHE_IMAGE_STYLE.get(client_obj.niche, 'professional photography')
        color = client_obj.brand_colors[0] if client_obj.brand_colors else '#333333'

        prompt = (
            f"{style}, {post.post_type} themed, brand color {color}, "
            f"Instagram post style, vibrant, high quality, no text overlay"
        )

        try:
            response = openai.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1024x1024",
                response_format="b64_json",
            )
            img_data = base64.b64decode(response.data[0].b64_json)
            img = Image.open(io.BytesIO(img_data)).convert('RGB')
            return img.resize(FEED_SIZE, Image.LANCZOS)
        except Exception as e:
            logger.error(f"GPT-Image generation failed for post {post.id}: {e}")
            return self._placeholder_image(color, FEED_SIZE)

    def composite_feed(self, base: Image.Image, business_name: str,
                       caption: str, cta: str,
                       logo_path: Optional[str] = None) -> Image.Image:
        img = base.copy().resize(FEED_SIZE, Image.LANCZOS)

        overlay = Image.new('RGBA', FEED_SIZE, (0, 0, 0, 0))
        bar = ImageDraw.Draw(overlay)
        bar.rectangle([(0, 820), (1080, 1080)], fill=(0, 0, 0, 160))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)

        draw.text((40, 835), business_name, fill='white')
        draw.text((40, 900), cta, fill='#FFD700')
        draw.text((40, 1050), "postado.com.br", fill=(200, 200, 200))

        if logo_path:
            try:
                logo = Image.open(logo_path).convert('RGBA')
                logo = logo.resize((120, 120), Image.LANCZOS)
                img.paste(logo, (920, 830), logo)
            except Exception as e:
                logger.warning(f"Logo paste failed: {e}")

        return img

    def to_stories(self, feed_img: Image.Image) -> Image.Image:
        stories = Image.new('RGB', STORIES_SIZE, (20, 20, 20))
        resized = feed_img.resize((1080, 1080), Image.LANCZOS)
        y_offset = (STORIES_SIZE[1] - 1080) // 2
        stories.paste(resized, (0, y_offset))
        return stories

    def save_to_bytes(self, img: Image.Image) -> bytes:
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        return buf.getvalue()

    def _placeholder_image(self, hex_color: str, size: tuple) -> Image.Image:
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
        except Exception:
            r, g, b = 80, 80, 80
        return Image.new('RGB', size, (r, g, b))
