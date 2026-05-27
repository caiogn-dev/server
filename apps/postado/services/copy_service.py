import json
import logging
import os
from openai import OpenAI
from apps.postado.models import PostadoPost, PostadoClient

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = 'https://integrate.api.nvidia.com/v1'
NVIDIA_API_KEY = os.environ.get('NVIDIA_API_KEY', '')
COPY_MODEL = os.environ.get('POSTADO_COPY_MODEL', 'moonshotai/kimi-k2.6')

NICHE_CONTEXT = {
    'restaurant': 'restaurante, comida, gastronomia, delivery',
    'salon': 'salão de beleza, cabelo, estética, cuidado pessoal',
    'store': 'loja, produtos, varejo, compras',
}

TONE_INSTRUCTION = {
    'professional': 'Tom formal e profissional. Use linguagem respeitosa e técnica.',
    'casual': 'Tom descontraído e amigável. Use emojis moderadamente.',
    'luxury': 'Tom sofisticado e exclusivo. Transmita exclusividade e qualidade premium.',
}

POST_TYPE_BRIEF = {
    'promo': 'Promoção ou desconto especial. Gere urgência. Inclua % de desconto fictício ou "oferta limitada".',
    'product': 'Destaque um produto ou serviço. Ressalte benefícios e diferenciais.',
    'testimonial': 'Depoimento de cliente satisfeito. Inclua aspas e sensação de autenticidade.',
    'engagement': 'Pergunta ou dica para engajar seguidores. Convide a comentar ou marcar alguém.',
    'behind_scenes': 'Bastidor do negócio. Humanize a marca, mostre a equipe ou processo.',
    'date': 'Relacionado a uma data comemorativa do mês. Conecte ao negócio.',
}

MONTH_NAMES_PT = {
    1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril',
    5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
    9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro',
}


class CopyService:
    def __init__(self):
        self.client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)

    def generate(self, post: PostadoPost) -> dict:
        client_obj: PostadoClient = post.pack.client
        niche_ctx = NICHE_CONTEXT.get(client_obj.niche, '')
        tone_inst = TONE_INSTRUCTION.get(client_obj.tone, '')

        if post.post_type == 'date':
            month_num = int(post.pack.month.split('-')[1])
            month_name = MONTH_NAMES_PT.get(month_num, 'do mês')
            type_brief = f"Relacionado a uma data comemorativa do mês de {month_name}. Conecte ao negócio."
        else:
            type_brief = POST_TYPE_BRIEF.get(post.post_type, '')

        extras = []
        if client_obj.description:
            extras.append(f"Sobre o negócio: {client_obj.description}")
        if client_obj.products:
            extras.append(f"Produtos/serviços destaque: {', '.join(client_obj.products[:8])}")
        if client_obj.target_audience:
            extras.append(f"Público-alvo: {client_obj.target_audience}")
        if client_obj.instagram_handle:
            extras.append(f"Instagram: @{client_obj.instagram_handle.lstrip('@')}")
        if client_obj.contact_info:
            ci = client_obj.contact_info
            if ci.get('phone'):
                extras.append(f"Telefone: {ci['phone']}")
            if ci.get('address'):
                extras.append(f"Endereço: {ci['address']}")
            if ci.get('delivery_link'):
                extras.append(f"Link delivery: {ci['delivery_link']}")
        if client_obj.brand_guidelines:
            extras.append(f"Diretrizes de marca: {client_obj.brand_guidelines}")
        extra_block = '\n'.join(extras)

        prompt = f"""Você é um copywriter especialista em redes sociais para {niche_ctx}.

Negócio: {client_obj.business_name}
Nicho: {niche_ctx}
{tone_inst}
{extra_block}

Crie conteúdo para o seguinte post:
Tipo: {type_brief}

Responda APENAS com JSON válido no formato:
{{"caption": "legenda completa (máx 150 palavras)", "cta": "chamada para ação curta (máx 10 palavras)", "hashtags": "5-8 hashtags relevantes separadas por espaço"}}"""

        try:
            response = self.client.chat.completions.create(
                model=COPY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            logger.error(f"CopyService.generate error for post {post.id}: {e}")
            return {
                "caption": f"Post especial do {client_obj.business_name}!",
                "cta": "Entre em contato",
                "hashtags": f"#{client_obj.niche} #oferta",
            }
