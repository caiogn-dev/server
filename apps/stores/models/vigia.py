"""Vigias: avisos curtos ao dono, decididos por regra e não por IA (16/10).

Desenho copiado do que funciona no mercado (Toast IQ Agents, alertas do
Metabase, a fila do trycompai/crm), adaptado a loja pequena que lê WhatsApp:

- A REGRA decide se há algo a dizer (SQL/Python, testável). Nada de LLM
  decidindo: o resumo de IA já errou o dia da semana duas vezes.
- Silêncio é o padrão. Sem fato novo, não sai mensagem.
- Teto: uma mensagem de manhã e um alerta por dia, no máximo três itens.
- Todo aviso guarda os números que o justificaram (`dados`) — "por que me
  avisou?" sempre tem resposta.
- Idempotência no banco: `chave` única por loja. Beat em dobro, retry ou dois
  workers não geram aviso repetido.
"""
import uuid

from django.db import models


def _dias_uteis():
    return [0, 1, 2, 3, 4]


class VigiaConfig(models.Model):
    """Configuração dos vigias de uma loja. Opt-in: nasce desligada."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.OneToOneField('stores.Store', on_delete=models.CASCADE, related_name='vigia_config')
    ativo = models.BooleanField(default=False)
    #: Telefone do dono/gerente que recebe os avisos (só dígitos, com DDI).
    telefone = models.CharField(max_length=20, blank=True, default='')
    #: "Receber no e-mail" (do Prefiro): cópia do resumo, com TODOS os avisos.
    #: Não depende da janela de 24 h nem do modelo aprovado na Meta.
    email = models.EmailField(blank=True, default='')
    #: Hora da mensagem da manhã, no fuso da loja.
    hora_resumo = models.TimeField(default='08:00')
    #: Hora a partir da qual "nenhum pedido hoje" vira alerta.
    hora_alerta = models.TimeField(default='12:30')
    #: Dias em que a loja abre (0 = segunda). Fora deles nada sai.
    dias = models.JSONField(default=_dias_uteis)
    #: Tipos desligados pelo dono. Lista de negação: vigia novo nasce ligado.
    desligados = models.JSONField(default=list, blank=True)
    #: Pausa pedida por "PARAR AVISOS" no WhatsApp ou pelo painel.
    pausado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_vigia_config'
        verbose_name = 'Configuração de vigias'
        verbose_name_plural = 'Configurações de vigias'

    def __str__(self):
        return f'Vigias de {self.store_id} ({"ligado" if self.ativo else "desligado"})'

    @property
    def em_operacao(self) -> bool:
        return self.ativo and self.pausado_em is None

    def tipo_ligado(self, tipo: str) -> bool:
        return tipo not in (self.desligados or [])


class VigiaEnvio(models.Model):
    """Uma mensagem ao dono. No máximo uma por (loja, dia, turno)."""

    class Turno(models.TextChoices):
        MANHA = 'manha', 'Manhã'
        ALERTA = 'alerta', 'Alerta'

    class Status(models.TextChoices):
        ENVIADO = 'enviado', 'Enviado'
        SO_PAINEL = 'so_painel', 'Só no painel'
        FALHOU = 'falhou', 'Falhou'
        SILENCIO = 'silencio', 'Nada a dizer'

    class Canal(models.TextChoices):
        TEXTO = 'texto', 'WhatsApp (conversa aberta)'
        MODELO = 'modelo', 'WhatsApp (modelo aprovado)'
        PAINEL = 'painel', 'Só no painel'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='vigia_envios')
    dia = models.DateField()
    turno = models.CharField(max_length=10, choices=Turno.choices)
    status = models.CharField(max_length=12, choices=Status.choices)
    canal = models.CharField(max_length=10, choices=Canal.choices, default=Canal.PAINEL)
    texto = models.TextField(blank=True, default='')
    telefone = models.CharField(max_length=20, blank=True, default='')
    mensagem_id = models.CharField(max_length=64, blank=True, default='')
    erro = models.CharField(max_length=300, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_vigia_envio'
        ordering = ['-criado_em']
        constraints = [
            models.UniqueConstraint(fields=['store', 'dia', 'turno'], name='vigia_envio_um_por_turno'),
        ]

    def __str__(self):
        return f'{self.store_id} {self.dia} {self.turno}: {self.status}'


class VigiaAviso(models.Model):
    """Um fato que uma regra achou. Aparece no painel mesmo se não for ao WhatsApp."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='vigia_avisos')
    tipo = models.CharField(max_length=32, db_index=True)
    #: Idempotência: ex. "resumo:2026-10-15", "sabor_em_queda:almondega:2026-W42".
    chave = models.CharField(max_length=160)
    #: Base do intervalo mínimo entre avisos do mesmo assunto (ex. o produto).
    grupo = models.CharField(max_length=160, db_index=True)
    prioridade = models.PositiveSmallIntegerField(default=5)
    titulo = models.CharField(max_length=120)
    texto = models.CharField(max_length=400)
    #: Os números que justificaram o aviso.
    dados = models.JSONField(default=dict, blank=True)
    envio = models.ForeignKey(
        VigiaEnvio, null=True, blank=True, on_delete=models.SET_NULL, related_name='avisos',
    )
    #: Resposta do dono no painel: útil (True), não útil (False), sem resposta (None).
    util = models.BooleanField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'store_vigia_aviso'
        ordering = ['-criado_em', '-prioridade']
        constraints = [
            models.UniqueConstraint(fields=['store', 'chave'], name='vigia_aviso_chave_unica'),
        ]

    def __str__(self):
        return f'{self.tipo}: {self.titulo}'
