"""O vínculo de uma loja com o iFood.

Desde 19/11/2026 o app é CENTRALIZADO (credencial da plataforma, ver
`ifood_oauth`): o que é da loja é só o `merchant_id` e as escolhas dela. Os
campos de token/userCode abaixo são do modelo distribuído antigo e ficaram
sem uso — não foram apagados para não exigir migration destrutiva.

UM APP, MUITOS RESTAURANTES. O Cardapidex é vendido para donos de restaurante,
e cada um tem o próprio cadastro no iFood. Por isso o modelo guarda o vínculo
por LOJA: as credenciais do aplicativo (clientId/clientSecret) são da
plataforma e ficam em settings; o que é de cada loja é a autorização que o
lojista deu e os tokens que vieram dela.
"""
import uuid

from django.db import models

from apps.core.fields import EncryptedCharField


class StoreIfoodIntegration(models.Model):
    """Autorização e tokens do iFood para uma loja.

    O TOKEN DURA 6 HORAS, e é por isso que `token_expires_at` existe e é
    consultado antes de cada uso. O OAuth do Mercado Pago neste mesmo projeto
    tinha a função de renovar escrita e sem nenhum caller: a loja conectava,
    funcionava, e pararia de vender meses depois sem ninguém entender por quê.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.OneToOneField(
        'stores.Store', on_delete=models.CASCADE, related_name='ifood',
    )

    #: O restaurante no iFood. Vem depois do vínculo, pela API de merchants.
    merchant_id = models.CharField(max_length=64, blank=True, default='')
    merchant_name = models.CharField(max_length=255, blank=True, default='')

    #: Só existe entre pedir o userCode e trocar pelo token. Perdê-lo obriga o
    #: lojista a recomeçar — e ele já saiu da tela.
    authorization_code_verifier = models.CharField(max_length=255, blank=True, default='')
    user_code = models.CharField(max_length=32, blank=True, default='')
    user_code_expires_at = models.DateTimeField(null=True, blank=True)

    # Credenciais de terceiro: vão cifradas, como as do Mercado Pago.
    access_token_encrypted = EncryptedCharField(max_length=2000, blank=True, default='')
    refresh_token_encrypted = EncryptedCharField(max_length=2000, blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)

    conectado = models.BooleanField(default=False)
    #: O motivo da última recusa. Integração de venda que falha calada é o
    #: pedido parando de entrar sem ninguém perceber.
    ultimo_erro = models.TextField(blank=True, default='')
    ultima_renovacao = models.DateTimeField(null=True, blank=True)

    # ── iFood Entrega (chamar entregador do iFood para pedido nosso) ──────
    #: Cobrar do cliente o frete que o iFood cota para o pino. Desligado = a
    #: tabela da loja continua valendo e o iFood só leva o pedido.
    frete_pelo_ifood = models.BooleanField(default=False)
    #: Somado à cotação do iFood antes de mostrar ao cliente (pode ser 0).
    acrescimo_frete = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class ChamarEntregador(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        CONFIRMADO = 'confirmado', 'Ao confirmar o pedido'
        PRONTO = 'pronto', 'Quando ficar pronto'

    chamar_entregador = models.CharField(
        max_length=12, choices=ChamarEntregador.choices, default=ChamarEntregador.MANUAL,
    )
    #: Com "ao confirmar", o iFood segura a alocação por este tempo para o
    #: entregador chegar junto com o pedido pronto (`preparationTime`).
    tempo_preparo_min = models.PositiveSmallIntegerField(default=15)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_ifood_integrations'
        verbose_name = 'Integração iFood'
        verbose_name_plural = 'Integrações iFood'

    def __str__(self):
        return f'iFood de {self.store.name}'

    # Os nomes curtos são o que o resto do sistema usa; o `_encrypted` é
    # detalhe de armazenamento e não deve vazar para os chamadores.
    @property
    def access_token(self) -> str:
        return self.access_token_encrypted or ''

    @access_token.setter
    def access_token(self, valor: str):
        self.access_token_encrypted = valor or ''

    @property
    def refresh_token(self) -> str:
        return self.refresh_token_encrypted or ''

    @refresh_token.setter
    def refresh_token(self, valor: str):
        self.refresh_token_encrypted = valor or ''
