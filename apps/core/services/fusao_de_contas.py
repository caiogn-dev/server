"""Funde as contas que são a mesma pessoa.

O CASO REAL (05/09): 8 pessoas com 17 contas na base. Todas pelo mesmo motivo
— o WhatsApp entrega o telefone sem o nono dígito e o site grava com ele, então
a mesma pessoa entrou por duas portas e virou dois logins. A ficha dela mostra
metade dos pedidos, o RFM a classifica em dois segmentos, e ela aparece duas
vezes em toda lista.

O cadastro de cliente (`StoreCustomer`) já tem trava de banco desde 04/09. Este
serviço trata a camada de baixo — a CONTA de login — que a trava não cobre.

QUEM SOBREVIVE: mais pedidos PAGOS; empate decide pelo mais antigo, que é o
"cliente desde" que os relatórios já contam.

E NÃO "a mais antiga vence": a conta nova costuma ter o dado melhor. A Yasmine
tem o e-mail real na conta de agosto e um placeholder interno na anterior. O
histórico decide quem fica; o dado bom migra para ela, venha de onde vier.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.core.models import UserProfile
from apps.core.utils import normalize_phone_number

logger = logging.getLogger(__name__)

User = get_user_model()

#: E-mails que o sistema inventa quando a pessoa entra sem informar um. Nunca
#: devem vencer um endereço de verdade nem aparecer para o cliente.
DOMINIOS_INTERNOS = (
    '@pastita.local', '@cardapidex.local', '@anonimizado.local',
    '@local.invalid', '@whatsapp.local', '@whatsapp.br',
    # `@whatsapp.bot` faltava e custou caro: a Elisângela tinha
    # `eliruppenthal@hotmail.com` numa conta e este endereço inventado na
    # outra. Como o inventado não estava na lista, ele passou por "de verdade"
    # e o e-mail real dela foi descartado na fusão (05/09).
    '@whatsapp.bot',
)


def _email_de_verdade(email: str) -> bool:
    valor = (email or '').strip().lower()
    return bool(valor) and not any(valor.endswith(d) for d in DOMINIOS_INTERNOS)


def _nome_de(user) -> str:
    return f'{user.first_name} {user.last_name}'.strip()


def _nome_de_verdade(nome: str) -> bool:
    """`cliente_5563...` é identidade interna, não nome de pessoa."""
    valor = (nome or '').strip()
    return bool(valor) and not valor.lower().startswith('cliente_')


def _letras_comuns(nome: str) -> int:
    """Quantas letras do alfabeto latino o nome tem, acentos incluídos.

    É como se escolhe o melhor nome, e não pelo tamanho.

    O nome que a pessoa usa no WhatsApp costuma vir enfeitado —
    "𝑬𝒍𝒊𝒔â𝒏𝒈𝒆𝒍𝒂 ®️𝒖𝒑𝒑𝒆𝒏𝒕𝒉𝒂𝒍" usa letras matemáticas do Unicode, que NÃO são
    letras comuns. Esse nome é mais longo que "Elisângela Ruppenthal", então
    uma regra de tamanho o manteria no painel para sempre, e ninguém
    conseguiria encontrá-la buscando pelo nome dela.

    Acento conta: "Gonçalves" não pode perder por causa do ç.
    """
    import unicodedata
    return sum(
        1 for ch in (nome or '')
        if ch.isalpha() and unicodedata.name(ch, '').startswith('LATIN ')
    )


@dataclass
class Plano:
    telefone: str
    fica: object
    saem: list = field(default_factory=list)

    def __str__(self) -> str:
        quem = _nome_de(self.fica) or self.fica.username
        return (
            f'{self.telefone}: fica #{self.fica.id} ({quem}) '
            f'| some {[f"#{u.id}" for u in self.saem]}'
        )


class FusaoDeContas:
    """Planeja e aplica a fusão. Planejar NUNCA escreve."""

    @staticmethod
    def _pagos(user) -> int:
        from apps.stores.models import StoreOrder
        return StoreOrder.objects.filter(customer=user, payment_status='paid').count()

    @classmethod
    def planejar(cls, apenas=None) -> list:
        """Devolve um plano por pessoa duplicada. Não toca no banco.

        `apenas`: lista de telefones (qualquer formato) para restringir.
        """
        alvo = {normalize_phone_number(t) for t in (apenas or [])} or None

        grupos = defaultdict(list)
        for perfil in UserProfile.objects.exclude(phone='').select_related('user'):
            canonico = normalize_phone_number(perfil.phone) or perfil.phone
            if alvo is None or canonico in alvo:
                grupos[canonico].append(perfil.user)

        planos = []
        for telefone, contas in sorted(grupos.items()):
            if len(contas) < 2:
                continue
            # Mais pedidos pagos vence; empate, a mais antiga.
            contas.sort(key=lambda u: (-cls._pagos(u), u.date_joined))
            planos.append(Plano(telefone=telefone, fica=contas[0], saem=contas[1:]))
        return planos

    # ── aplicação ───────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def aplicar(cls, planos: list) -> int:
        fundidas = 0
        for plano in planos:
            for perdedora in plano.saem:
                cls._absorver(plano.fica, perdedora, plano.telefone)
                fundidas += 1
            plano.fica.save()
        return fundidas

    @classmethod
    def _absorver(cls, fica, sai, telefone: str) -> None:
        cls._melhor_dado(fica, sai)
        cls._fundir_cadastros(fica, sai, telefone)
        cls._fundir_fidelidade(fica, sai)
        cls._repontar_o_resto(fica, sai)

        # O perfil do perdedor sai junto com ele; o do vencedor fica com o
        # telefone canônico, que é o que a trava do cadastro já usa.
        UserProfile.objects.filter(user=sai).delete()
        UserProfile.objects.filter(user=fica).update(phone=telefone)
        sai.delete()

    @staticmethod
    def _melhor_dado(fica, sai) -> None:
        """O dado bom migra, venha de qual conta vier.

        Quem VENCE é decidido pelo histórico de compra; isso não quer dizer que
        ela tenha o melhor cadastro. A conta criada pelo OTP nasce com e-mail
        inventado (`84195663@local.invalid`) e nome vazio.
        """
        if not _email_de_verdade(fica.email) and _email_de_verdade(sai.email):
            fica.email = sai.email

        nome_dela, nome_dele = _nome_de(fica), _nome_de(sai)
        # Mais LETRAS COMUNS ganha, não mais caracteres: "Yasmine Ulisses" diz
        # mais que "Yasmine", e "Elisângela Ruppenthal" vence o nome enfeitado
        # do WhatsApp mesmo sendo mais curto em caracteres.
        if _nome_de_verdade(nome_dele) and (
            not _nome_de_verdade(nome_dela)
            or _letras_comuns(nome_dele) > _letras_comuns(nome_dela)
        ):
            fica.first_name, fica.last_name = sai.first_name, sai.last_name

    @staticmethod
    def _fundir_cadastros(fica, sai, telefone: str) -> None:
        """`StoreCustomer` tem unique(store,user) E unique(store,phone).

        As duas contas podem ter cadastro na MESMA loja — repontar estoura nas
        duas travas. Onde houver colisão, funde somando os contadores; onde não
        houver, repointa.
        """
        from apps.stores.models.customer import StoreCustomer, StoreCustomerAddress

        do_vencedor = {c.store_id: c for c in StoreCustomer.objects.filter(user=fica)}
        for cadastro in StoreCustomer.objects.filter(user=sai):
            irmao = do_vencedor.get(cadastro.store_id)
            if irmao is None:
                cadastro.user = fica
                cadastro.phone = telefone
                cadastro.save(update_fields=['user', 'phone'])
                do_vencedor[cadastro.store_id] = cadastro
                continue

            irmao.total_orders = (irmao.total_orders or 0) + (cadastro.total_orders or 0)
            irmao.total_spent = (irmao.total_spent or 0) + (cadastro.total_spent or 0)
            if cadastro.last_order_at and (
                not irmao.last_order_at or cadastro.last_order_at > irmao.last_order_at
            ):
                irmao.last_order_at = cadastro.last_order_at
            irmao.phone = telefone
            StoreCustomerAddress.objects.filter(customer=cadastro).update(customer=irmao)
            cadastro.delete()
            irmao.save()

    @staticmethod
    def _fundir_fidelidade(fica, sai) -> None:
        """unique(store,user), e aqui é SALDO DE CARIMBO: somar, não descartar.

        Perder carimbo de cliente numa limpeza de banco é a loja tomando de
        volta algo que a pessoa já ganhou — e ela descobre no balcão.
        """
        try:
            from apps.stores.models import StoreLoyaltyAccount
        except ImportError:
            return

        somaveis = [
            f.name for f in StoreLoyaltyAccount._meta.fields
            if f.get_internal_type() in ('IntegerField', 'PositiveIntegerField', 'DecimalField')
        ]
        do_vencedor = {c.store_id: c for c in StoreLoyaltyAccount.objects.filter(user=fica)}
        for conta in StoreLoyaltyAccount.objects.filter(user=sai):
            irmao = do_vencedor.get(conta.store_id)
            if irmao is None:
                conta.user = fica
                conta.save(update_fields=['user'])
                do_vencedor[conta.store_id] = conta
                continue
            for campo in somaveis:
                atual = getattr(irmao, campo, None)
                extra = getattr(conta, campo, None)
                if atual is not None and extra is not None:
                    setattr(irmao, campo, atual + extra)
            conta.delete()
            irmao.save()

    @staticmethod
    def _repontar_o_resto(fica, sai) -> None:
        """Pedido, carrinho, loja, notificação, token — tudo passa para quem fica.

        `Store.owner` incluído de propósito: duas das contas são donas de loja,
        e deletar sem repontar levaria a loja junto.

        Colisão de chave única (carrinho ativo por loja, por exemplo) descarta a
        linha do perdedor em vez de derrubar a fusão inteira — o que se perde
        ali é estado de rascunho, nunca compra.
        """
        from django.db.utils import IntegrityError

        ja_tratados = {'StoreCustomer', 'StoreLoyaltyAccount', 'UserProfile'}
        for rel in User._meta.related_objects:
            modelo = rel.related_model
            if modelo.__name__ in ja_tratados:
                continue
            campo = rel.field.name
            for linha in modelo.objects.filter(**{campo: sai}):
                setattr(linha, campo, fica)
                try:
                    with transaction.atomic():
                        linha.save(update_fields=[campo])
                except IntegrityError:
                    logger.info(
                        'fusão: %s #%s colidiu ao repontar; descartado',
                        modelo.__name__, linha.pk,
                    )
                    with transaction.atomic():
                        linha.delete()
