"""Cria (ou atualiza) o agente de IA de uma loja e liga a IA para ela.

Pedido pelo dono em 13/ago: "MELHORE O FLUXO E CRIE O AGENTE DA CE-SALADAS PARA
USAR IA". O fluxo foi melhorado — triagem, classificador, guarda contra
alucinação — mas o AGENTE nunca foi criado. A Cê Saladas seguiu com
`use_ai_agent = False` e `default_agent = None`, ou seja, 100% determinística.

Ligar a IA exige QUATRO coisas ao mesmo tempo, e faltar uma deixa tudo
silenciosamente desligado — foi assim que o agente ficou `inactive` em 13
perfis sem ninguém notar:

  1. um `Agent` com `is_active=True` E `status='active'`
     (`_agent_is_runtime_available` exige os dois);
  2. `CompanyProfile.default_agent` apontando para ele;
  3. `CompanyProfile.use_ai_agent = True`;
  4. `WHATSAPP_FORCE_DISABLE_LLM` desligado no ambiente.

Este comando cuida de 1–3 e CONFERE a 4, em vez de deixar o dono descobrir
depois que o bot continua respondendo por regex.

O `system_prompt` é a camada de VOZ E REGRAS DA LOJA: ele ajusta tom e
política, e NÃO substitui as regras de ferramenta e de fluxo de pedido, que
vêm acima em `_build_system_prompt`. Escrever instrução de tool aqui seria
brigar com o motor.

    python manage.py criar_agente_da_loja --loja ce-saladas
    python manage.py criar_agente_da_loja --loja ce-saladas --ligar
    python manage.py criar_agente_da_loja --loja ce-saladas --desligar
"""
from django.core.management.base import BaseCommand, CommandError

#: Modelo do NIM. Igual ao do agente que já existe — trocar de modelo é decisão
#: separada de criar o agente, e misturar as duas esconde qual das duas quebrou.
MODELO = 'deepseek-ai/deepseek-v4-flash-0731'
BASE_URL = 'https://integrate.api.nvidia.com/v1'

#: Voz e política. Curto de propósito: cada linha aqui compete por atenção com
#: as regras de motor, e prompt longo dilui as duas.
VOZ_PADRAO = """Você atende pela {loja}, em Palmas.

TOM
- Fale como gente, no ritmo do WhatsApp: frases curtas, calor humano, sem
  formalidade de e-mail e sem parecer catálogo falante.
- Uma pergunta por vez. Cliente não responde formulário.
- Emoji com parcimônia — no máximo um por mensagem.

O QUE NUNCA FAZER
- Nunca invente ingrediente, receita, valor nutricional ou informação de
  alérgeno. Se não estiver no cardápio, diga que vai confirmar.
- Nunca prometa prazo de entrega que você não recebeu do sistema.
- Nunca diga que um produto é "sem glúten", "sem lactose" ou "vegano" por
  dedução. Ausência de informação não é ausência do ingrediente.
- Nunca invente desconto, cupom ou frete grátis.

COMO FECHAR VENDA
- Cliente decidido: não empurre mais nada, feche.
- Cliente perdido: sugira no máximo duas opções, com o preço.
- Preço e taxa de entrega saem do sistema. Não estime, não arredonde.

COMBO — CONTE, NÃO COMPLETE
- Some exatamente o que o cliente pediu. Se ele disse "1 frango, 2 queridinha,
  1 almôndega", são QUATRO — não cinco.
- Faltando sabor, diga quantos faltam e pergunte quais. NUNCA repita um sabor
  para fechar a conta, e nunca escolha por ele: quem recebe a salada é ele.
- Passou do limite, peça a lista de novo. Não corte por conta própria.
- Só chame a ferramenta de adicionar quando a conta bater."""


class Command(BaseCommand):
    help = 'Cria/atualiza o agente de IA de uma loja e liga a IA para ela.'

    def add_arguments(self, parser):
        parser.add_argument('--loja', required=True, help='slug da loja')
        parser.add_argument('--nome', help='nome do atendente (padrão: nome da loja)')
        parser.add_argument(
            '--ligar', action='store_true',
            help='liga `use_ai_agent` — a partir daí a IA responde clientes reais',
        )
        parser.add_argument(
            '--desligar', action='store_true',
            help='desliga `use_ai_agent` sem apagar o agente',
        )

    def handle(self, *args, **opts):
        from django.conf import settings

        from apps.agents.models import Agent
        from apps.automation.models import CompanyProfile
        from apps.stores.models import Store

        loja = Store.objects.filter(slug=opts['loja']).first()
        if loja is None:
            raise CommandError(f"Loja {opts['loja']!r} não existe.")

        perfil = CompanyProfile.objects.filter(store=loja).first()
        if perfil is None:
            raise CommandError(
                f'{loja.name} não tem CompanyProfile — sem ele não há onde ligar a IA.'
            )

        if opts['desligar']:
            perfil.use_ai_agent = False
            perfil.save(update_fields=['use_ai_agent'])
            self.stdout.write(self.style.WARNING(
                f'IA DESLIGADA para {loja.name}. O agente continua cadastrado.'
            ))
            return

        nome = opts.get('nome') or f'Atendente {loja.name}'

        agente, criado = Agent.objects.update_or_create(
            name=nome,
            defaults={
                'description': f'Agente de atendimento da {loja.name} (WhatsApp).',
                'provider': 'nvidia',
                'model_name': MODELO,
                'base_url': BASE_URL,
                # Temperatura baixa: atendimento não é criação literária, e
                # modelo criativo é modelo que inventa ingrediente.
                'temperature': 0.4,
                'max_tokens': 700,
                'system_prompt': VOZ_PADRAO.format(loja=loja.name),
                # OS DOIS, sempre. `_agent_is_runtime_available` exige
                # `is_active` E `status == 'active'`; setar só um deixa o
                # agente cadastrado e mudo.
                'is_active': True,
                'status': 'active',
            },
        )
        self.stdout.write(
            f'{"Criado" if criado else "Atualizado"}: {agente.name} '
            f'({agente.provider} / {agente.model_name})'
        )

        perfil.default_agent = agente
        campos = ['default_agent']
        if opts['ligar']:
            perfil.use_ai_agent = True
            campos.append('use_ai_agent')
        perfil.save(update_fields=campos)

        self._conferir(loja, perfil, agente, settings)

    def _conferir(self, loja, perfil, agente, settings):
        """Diz em voz alta se a IA vai realmente responder. Faltar um item
        deixa tudo desligado em silêncio — é o modo de falha desta feature."""
        from apps.automation.services.context_service import AutomationContextService

        checagens = [
            ('agente ativo em runtime', agente.is_active and agente.status == 'active'),
            ('perfil aponta para o agente', perfil.default_agent_id == agente.id),
            ('use_ai_agent ligado', bool(perfil.use_ai_agent)),
            ('LLM não bloqueado no ambiente',
             str(getattr(settings, 'WHATSAPP_FORCE_DISABLE_LLM', 'false')).lower()
             not in {'1', 'true', 'yes', 'on'}),
            ('chave da NVIDIA presente',
             bool(getattr(settings, 'NVIDIA_API_KEY', '') or agente.api_key)),
        ]
        for rotulo, ok in checagens:
            self.stdout.write(f'  [{"ok" if ok else "FALTA"}] {rotulo}')

        vale = AutomationContextService.is_ai_enabled(
            store=loja, company=perfil, allow_env_override=False,
        )
        if vale:
            self.stdout.write(self.style.SUCCESS(
                f'\nA IA está LIGADA para {loja.name} — ela vai responder clientes reais.\n'
                f'Para desligar na hora: '
                f'manage.py criar_agente_da_loja --loja {loja.slug} --desligar'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f'\nAgente cadastrado, mas a IA NÃO está respondendo. '
                f'Use --ligar (ou resolva o que está marcado como FALTA acima).'
            ))
