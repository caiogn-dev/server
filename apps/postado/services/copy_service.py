import json
import logging
from anthropic import Anthropic
from apps.postado.models import PostadoPost, PostadoClient

logger = logging.getLogger(__name__)

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
    'date': 'Relacionado a uma data comemorativa do mês de junho. Conecte ao negócio.',
}


class CopyService:
    def __init__(self):
        self.client = Anthropic()

    def generate(self, post: PostadoPost) -> dict:
        client_obj: PostadoClient = post.pack.client
        niche_ctx = NICHE_CONTEXT.get(client_obj.niche, '')
        tone_inst = TONE_INSTRUCTION.get(client_obj.tone, '')
        type_brief = POST_TYPE_BRIEF.get(post.post_type, '')

        prompt = f"""Você é um copywriter especialista em redes sociais para {niche_ctx}.

Negócio: {client_obj.business_name}
Nicho: {niche_ctx}
{tone_inst}

Crie conteúdo para o seguinte post:
Tipo: {type_brief}

Responda APENAS com JSON válido no formato:
{{"caption": "legenda completa (máx 150 palavras)", "cta": "chamada para ação curta (máx 10 palavras)", "hashtags": "5-8 hashtags relevantes separadas por espaço"}}"""

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
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
