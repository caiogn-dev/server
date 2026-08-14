"""Classificador de intenção via NVIDIA NIM.

É a peça que a triagem chama quando o catálogo e o regex não resolveram. Ele
não conversa com o cliente: devolve um rótulo e some. Quem escreve a resposta
continua sendo o handler determinístico.

Três restrições que vêm da história deste projeto, não de preferência:

- **NVIDIA NIM.** Produção nunca chamou Anthropic nem OpenAI, e a chave já está
  no ambiente (`NVIDIA_API_KEY`), servindo o agente que existe hoje.
- **Timeout curto.** O bot já teve 3 minutos de latência e resposta descartada
  no timeout de 90s. Classificador lento é pior que classificador errado — o
  cliente já foi embora quando a resposta chega.
- **Sem tools.** O agente com ferramentas de escrita continua existindo para o
  consultivo; aqui, dar ao modelo o poder de mexer no carrinho seria recriar
  por outro caminho o pedido errado que motivou tudo isto.
"""
import json
import logging
import os
import re
from typing import Optional

from apps.automation.services.triagem import Decisao, Intencao

logger = logging.getLogger(__name__)

#: Segundos. Curto de propósito: acima disto o handler determinístico responde
#: melhor do que a espera, porque responder rápido e mais ou menos ganha de
#: responder certo depois que a pessoa desistiu.
TIMEOUT_PADRAO = 4

#: Classificar é escolher entre quatro rótulos — não precisa do modelo grande.
#:
#: Medido contra o NIM real, com gabarito de 10 frases da conversa da Yeda:
#:
#:   llama-3.1-8b    acerto  8/10   mediana   431 ms
#:   llama-3.1-70b   acerto  6/10   mediana 9.521 ms
#:
#: O 70b não erra por burrice: ele estoura o tempo. Quatro das dez viraram
#: FALHOU. Num roteador que roda no caminho do cliente, o modelo grande é a
#: escolha PIOR nos dois eixos ao mesmo tempo.
#:
#: Fica separado de NVIDIA_MODEL_NAME de propósito: o agente conversacional
#: continua no modelo grande, onde qualidade de texto importa e o tempo é menos
#: crítico.
MODELO_PADRAO = 'meta/llama-3.1-8b-instruct'

_ROTULOS = {
    'saudacao': Intencao.SAUDACAO,
    'item': Intencao.ITEM,
    'observacao': Intencao.OBSERVACAO,
    'consultiva': Intencao.CONSULTIVA,
}

_INSTRUCAO = """Você classifica mensagens de clientes de um delivery. Você NÃO
responde ao cliente — outro sistema faz isso. Sua saída é APENAS um JSON.

Rótulos possíveis:
- "item": a pessoa quer ACRESCENTAR algo ao pedido (cita produto, "quero X",
  "mais um Y", "manda mais 2")
- "observacao": recado para a cozinha sobre o que JÁ foi pedido, quase sempre
  uma retirada ("sem cebola", "capricha no molho", "bem passado")
- "consultiva": pergunta, dúvida, reclamação, conversa
- "saudacao": só cumprimento

Regras que não se quebram:
- "sem X", "tirar X", "não quero X" é SEMPRE observacao, nunca item — mesmo que
  X exista no cardápio.
- Se a pessoa nomeia algo que não está no cardápio abaixo, é consultiva.
- Na dúvida entre item e consultiva, escolha consultiva: acrescentar item
  errado custa dinheiro, responder de mais custa uma mensagem.

Responda SÓ com:
{"intencao": "<rótulo>", "confianca": <0 a 1>}"""


def _decisao_do_json(bruto) -> Optional[Decisao]:
    """Extrai a decisão do que o modelo respondeu.

    Modelo aberto embrulha em ```json, escreve "Claro!" antes e explica depois —
    é o caso comum, não a exceção. Recusar em vez de adivinhar quando o rótulo
    não existe: alucinação virando intenção é como item errado entra no pedido.
    """
    if not bruto:
        return None
    texto = str(bruto)
    achado = re.search(r'\{.*?\}', texto, re.S)
    if not achado:
        return None
    try:
        dados = json.loads(achado.group(0))
    except (ValueError, TypeError):
        return None

    intencao = _ROTULOS.get(str(dados.get('intencao', '')).strip().lower())
    if intencao is None:
        logger.info('[classificador] rótulo desconhecido: %r', dados.get('intencao'))
        return None

    try:
        confianca = float(dados.get('confianca', 0.7))
    except (TypeError, ValueError):
        confianca = 0.7

    return Decisao(intencao=intencao, confianca=max(0.0, min(1.0, confianca)),
                   origem='llm')


class ClassificadorNIM:
    """Chamável que a triagem injeta. Devolve `Decisao` ou None."""

    def __init__(self, timeout: int = TIMEOUT_PADRAO):
        self.timeout = timeout
        self._modelo = None

    def _carregar(self):
        if self._modelo is not None:
            return self._modelo
        from django.conf import settings
        from langchain_openai import ChatOpenAI

        chave = os.getenv('NVIDIA_API_KEY') or getattr(settings, 'NVIDIA_API_KEY', '')
        if not chave:
            return None
        self._modelo = ChatOpenAI(
            model=os.getenv('NVIDIA_MODELO_CLASSIFICADOR')
            or getattr(settings, 'NVIDIA_MODELO_CLASSIFICADOR', MODELO_PADRAO),
            # Zero: classificar é escolher entre quatro rótulos, não criar.
            temperature=0,
            max_tokens=60,
            timeout=self.timeout,
            # Sem isto o teto é de mentira: o cliente tenta de novo sozinho e
            # cada tentativa ganha o timeout cheio. Medido contra o NIM real,
            # uma classificação levou 9.869 ms com timeout de 6s configurado.
            # A segunda tentativa chega depois que o cliente desistiu.
            max_retries=0,
            api_key=chave,
            base_url=os.getenv('NVIDIA_API_BASE_URL')
            or 'https://integrate.api.nvidia.com/v1',
        )
        return self._modelo

    def __call__(self, texto, *, store=None, esperando=None) -> Optional[Decisao]:
        modelo = self._carregar()
        if modelo is None:
            logger.info('[classificador] NVIDIA_API_KEY ausente — seguindo sem LLM')
            return None

        prompt = self._prompt(texto, store, esperando)
        try:
            resposta = modelo.invoke(prompt)
        except Exception as exc:
            # Qualquer falha é a mesma decisão: sair de cena. A triagem segue
            # determinística e o cliente recebe alguma coisa.
            logger.warning('[classificador] falhou (%s) — seguindo sem LLM', exc)
            return None

        return _decisao_do_json(getattr(resposta, 'content', resposta))

    def _prompt(self, texto, store, esperando) -> str:
        partes = [_INSTRUCAO]
        cardapio = self._cardapio(store)
        if cardapio:
            # Sem o catálogo o modelo classifica "quero uma coxinha" como item
            # numa loja que só vende salada.
            partes.append(f'\nCardápio desta loja:\n{cardapio}')
        if esperando == 'observacao':
            partes.append(
                '\nContexto: o pedido já está montado e o sistema perguntou se '
                'há alguma observação.'
            )
        partes.append(f'\nMensagem do cliente:\n{texto}')
        return '\n'.join(partes)

    @staticmethod
    def _cardapio(store, limite: int = 40) -> str:
        if store is None:
            return ''
        try:
            from apps.stores.models import StoreCombo, StoreProduct

            nomes = [
                *StoreProduct.disponiveis(store)
                .values_list('name', flat=True)[:limite],
                *StoreCombo.objects.filter(store=store, is_active=True)
                .values_list('name', flat=True)[:limite],
            ]
            return '\n'.join(f'- {n}' for n in nomes)
        except Exception as exc:  # pragma: no cover - defensivo
            logger.warning('[classificador] não consegui montar o cardápio: %s', exc)
            return ''
