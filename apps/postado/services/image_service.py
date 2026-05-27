import io
import os
import logging
from pathlib import Path
from typing import Optional
import requests
from PIL import Image, ImageDraw, ImageFont
from apps.postado.models import PostadoPost, PostadoClient

logger = logging.getLogger(__name__)

FEED_SIZE = (1080, 1080)
STORIES_SIZE = (1080, 1920)

_FONTS_DIR = Path(__file__).resolve().parent.parent / 'fonts'
_FONT_BOLD = str(_FONTS_DIR / 'Poppins-Bold.ttf')
_FONT_SEMI = str(_FONTS_DIR / 'Poppins-SemiBold.ttf')
_FONT_REG  = str(_FONTS_DIR / 'Poppins-Regular.ttf')

_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&model=flux&nologo=true&enhance=true"

_DALLE_PROMPTS = {
    'restaurant': {
        'promo': (
            "Professional food photography for a Brazilian restaurant promotion. "
            "A beautifully plated dish on a dark slate or marble surface, soft golden bokeh background, "
            "dramatic side lighting creating depth and shadow, garnished with fresh herbs, "
            "steam wisps, appetizing colors. Editorial magazine quality. Square format. No text, no people."
        ),
        'product': (
            "Professional hero shot food photography for a Brazilian restaurant. "
            "Single perfectly plated dish centered, overhead or 45-degree angle, "
            "natural linen napkin and artisan cutlery as props, fresh ingredients scattered artfully, "
            "warm neutral background. Michelin-star presentation style. No text, no people."
        ),
        'testimonial': (
            "Warm inviting restaurant interior ambiance photograph. "
            "Soft candlelight, blurred diners in background, table setting with wine glasses and fresh flowers, "
            "shallow depth of field, golden hour mood. Fine dining aesthetic. No text, no faces visible."
        ),
        'engagement': (
            "Flat lay food photography of a colorful spread of dishes and ingredients. "
            "Overhead shot on textured white or marble surface, vibrant fresh produce, "
            "ceramic bowls with sauces, rustic wooden spoons. Lifestyle blog aesthetic. No text."
        ),
        'behind_scenes': (
            "Behind-the-scenes kitchen photography in a professional restaurant. "
            "Chef's hands artfully plating a dish, stainless steel kitchen, "
            "motion blur on background activity, warm tungsten lighting. Authentic and dynamic. No faces visible."
        ),
        'date': (
            "Festive table setting for a special occasion at a Brazilian restaurant. "
            "Seasonal decorations, elegant dishware, soft bokeh lights, celebratory mood, "
            "warm tones. Editorial lifestyle quality. No text, no faces."
        ),
    },
    'salon': {
        'promo': (
            "Luxury beauty salon promotion photography. "
            "Elegant hair care products arranged on marble with fresh flowers, "
            "soft pink and gold tones, spa-like atmosphere. High-end editorial. No text, no faces."
        ),
        'product': (
            "Professional beauty product flat lay photography. "
            "Premium hair care or beauty products on white marble with botanicals, "
            "clean minimalist aesthetic, natural light, soft shadows. No text."
        ),
        'testimonial': (
            "Elegant beauty salon interior with warm lighting. "
            "Styling stations, mirrors with soft reflections, fresh flowers, "
            "luxurious decor. Aspirational and inviting. No people visible."
        ),
        'engagement': (
            "Close-up of beautiful healthy hair with soft backlighting. "
            "Rich texture and shine, natural tones, clean background. "
            "Professional beauty editorial quality. No faces."
        ),
        'behind_scenes': (
            "Candid behind-the-scenes at a beauty salon. "
            "Hands working with professional styling tools, warm light, blurred background. "
            "Authentic and skilled. No faces visible."
        ),
        'date': (
            "Special occasion beauty and glamour flat lay. "
            "Seasonal flowers, beauty accessories, soft pastel colors, "
            "elegant feminine aesthetic. No text."
        ),
    },
    'store': {
        'promo': (
            "Professional product promotion photography for retail. "
            "Products arranged on clean white or gradient background, "
            "bold composition, dramatic lighting, modern commercial aesthetic. No text."
        ),
        'product': (
            "Hero product shot for retail store. "
            "Single product centered, studio lighting, clean shadow, "
            "lifestyle context props, premium feel. Commercial photography standard. No text."
        ),
        'testimonial': (
            "Happy customer lifestyle photography in a modern retail context. "
            "Person using product (face not visible), natural light, candid feel. "
            "Warm and authentic. No text."
        ),
        'engagement': (
            "Lifestyle flat lay for retail brand. "
            "Products with complementary lifestyle items, textured background, "
            "aspirational and relatable. No text."
        ),
        'behind_scenes': (
            "Behind-the-scenes of a retail store or warehouse. "
            "Products being handled, organized shelves, team activity blurred in background. "
            "Authentic business aesthetic. No faces visible."
        ),
        'date': (
            "Seasonal retail display with festive decorations. "
            "Products styled for the occasion, warm celebratory colors. "
            "Commercial editorial quality. No text."
        ),
    },
}


def _get_dalle_prompt(post: PostadoPost, client_obj: PostadoClient) -> str:
    niche = client_obj.niche or 'restaurant'
    post_type = post.post_type or 'product'
    niche_prompts = _DALLE_PROMPTS.get(niche, _DALLE_PROMPTS['restaurant'])
    base = niche_prompts.get(post_type, niche_prompts.get('product', ''))

    extras = []
    if client_obj.products:
        products = ', '.join(client_obj.products[:3])
        extras.append(f"featuring {products}")
    if client_obj.brand_colors:
        extras.append(f"accent color palette inspired by {client_obj.brand_colors[0]}")

    if extras:
        return f"{base} {', '.join(extras)}."
    return base


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _draw_text_shadow(draw, pos, text, font, fill):
    x, y = pos
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)


class ImageService:
    def generate_base_image(self, post: PostadoPost, caption: str) -> Image.Image:
        client_obj: PostadoClient = post.pack.client
        prompt = _get_dalle_prompt(post, client_obj)

        try:
            encoded = requests.utils.quote(prompt)
            url = _POLLINATIONS_BASE.format(prompt=encoded)
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert('RGB')
            return img.resize(FEED_SIZE, Image.LANCZOS)
        except Exception as e:
            logger.error(f"Pollinations generation failed for post {post.id}: {e}")
            return self._placeholder_image(
                client_obj.brand_colors[0] if client_obj.brand_colors else '#2d6a4f',
                FEED_SIZE,
            )

    def composite_feed(self, base: Image.Image, business_name: str,
                       caption: str, cta: str,
                       logo_path: Optional[str] = None) -> Image.Image:
        img = base.copy().resize(FEED_SIZE, Image.LANCZOS)

        # Smooth bottom gradient (no hard rectangle)
        overlay = Image.new('RGBA', FEED_SIZE, (0, 0, 0, 0))
        ov = ImageDraw.Draw(overlay)
        grad_start = 680
        for y in range(grad_start, 1080):
            alpha = int(215 * ((y - grad_start) / (1080 - grad_start)) ** 1.3)
            ov.line([(0, y), (1080, y)], fill=(0, 0, 0, min(alpha, 215)))

        # Top strip for brand name
        ov.rectangle([(0, 0), (1080, 88)], fill=(0, 0, 0, 150))

        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)

        f_name  = _load_font(_FONT_BOLD, 44)
        f_cta   = _load_font(_FONT_BOLD, 54)
        f_hook  = _load_font(_FONT_SEMI, 32)
        f_small = _load_font(_FONT_REG,  24)

        # Brand name top
        _draw_text_shadow(draw, (44, 22), business_name.upper(), f_name, fill='white')

        # Hook — first short sentence of caption
        hook = caption.split('.')[0].split('!')[0].split('\n')[0].strip()
        hook = hook[:54] + '…' if len(hook) > 54 else hook
        _draw_text_shadow(draw, (44, 730), hook, f_hook, fill=(230, 230, 230))

        # CTA — big, gold
        cta_text = cta[:38] + '…' if len(cta) > 38 else cta
        _draw_text_shadow(draw, (44, 810), cta_text, f_cta, fill='#FFD700')

        # Watermark
        draw.text((44, 1044), "postado.com.br", font=f_small, fill=(150, 150, 150))

        if logo_path:
            try:
                logo = Image.open(logo_path).convert('RGBA').resize((88, 88), Image.LANCZOS)
                img.paste(logo, (956, 8), logo)
            except Exception as e:
                logger.warning(f"Logo paste failed: {e}")

        return img

    def to_stories(self, feed_img: Image.Image) -> Image.Image:
        stories = Image.new('RGB', STORIES_SIZE, (12, 12, 12))
        stories.paste(feed_img.resize((1080, 1080), Image.LANCZOS), (0, 420))
        return stories

    def save_to_bytes(self, img: Image.Image) -> bytes:
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
        return buf.getvalue()

    def _placeholder_image(self, hex_color: str, size: tuple) -> Image.Image:
        try:
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        except Exception:
            r, g, b = 45, 106, 79
        img = Image.new('RGB', size, (r, g, b))
        overlay = Image.new('RGBA', size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        for i in range(0, min(size) // 2, 4):
            alpha = int(60 * (i / (min(size) // 2)))
            d.rectangle([i, i, size[0]-i, size[1]-i], outline=(0, 0, 0, alpha))
        return Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
