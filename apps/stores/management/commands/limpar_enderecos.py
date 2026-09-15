"""Faxina do caderno de endereços dos clientes da loja.

Sem `--aplicar` só mostra o que faria. Com `--aplicar`, grava antes uma cópia
JSON de todo endereço que vai mudar ou sumir (`--backup`).

O que faz, por cliente:
1. Rua empilhada volta a ser rua (`rua_sem_cauda`) — o caso da Flávia.
2. Endereço sem rua, número e complemento é apagado (não serve para entregar).
3. Mesmo lugar repetido (`chave_do_lugar`) vira um só: fica o padrão, senão o
   mais novo, e os campos vazios dele são completados pelos que saem.
4. Exatamente um padrão.
"""
import json
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.services.customer_identity import CustomerIdentityService as CIS
from apps.stores.models import StoreCustomerAddress

CAMPOS = ('label', 'street', 'number', 'complement', 'neighborhood', 'city', 'state',
          'zip_code', 'reference', 'formatted')


def _foto(a):
    return {'id': str(a.id), 'customer': str(a.customer_id), 'is_default': a.is_default,
            **{c: getattr(a, c) for c in CAMPOS}}


def _acertar_padrao(todos, ficam):
    """Um padrão só — sem inventar padrão onde nunca houve.

    Mexe apenas quando sobra mais de um padrão, ou quando o padrão existia e
    foi apagado (vazio/repetido) e nenhum dos que ficam é padrão. Cliente que
    nunca teve endereço padrão continua sem: a simulação de 15/set queria
    marcar 143 no caderno do PDV, trocando a sugestão de endereço de gente que
    ninguém pediu para mudar.
    """
    if not ficam:
        return {}
    atuais = [a for a in ficam if a.is_default]
    tinha_padrao = any(a.is_default for a in todos)
    if len(atuais) == 1 or (not atuais and not tinha_padrao):
        return {}
    escolhido = max(atuais or ficam, key=lambda x: x.created_at)
    return {a.id: (a, a is escolhido) for a in ficam if a.is_default != (a is escolhido)}


def _foto_caderno(a):
    return {'id': str(a.id), 'unified_user': str(a.unified_user_id), 'tenant': str(a.tenant_id),
            'is_default': a.is_default, **{c: getattr(a, c) for c in
            ('label', 'street', 'number', 'complement', 'neighborhood', 'city', 'state', 'zip_code')}}


def _desempilhar_texto(texto: str) -> str:
    """"A, 9, X - B, C, UF, 9, X - B, C, UF, 9 - X · B" → primeira ocorrência só.

    O perfil guarda o endereço como TEXTO formatado (sem número/complemento
    separados), então a regra por peças não serve. Quando o mesmo trecho de
    ", <número>, " aparece mais de uma vez, fica tudo até a segunda ocorrência.
    """
    import re as _re
    m = _re.search(r', (\S{1,20}), ', texto or '')
    if not m:
        return texto
    marcador = m.group(0)
    primeira = texto.find(marcador)
    segunda = texto.find(marcador, primeira + len(marcador))
    if segunda == -1:
        return texto
    return texto[:segunda].rstrip(' ,')


class Command(BaseCommand):
    help = 'Limpa rua empilhada, apaga endereço vazio e junta o mesmo lugar repetido.'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true')
        parser.add_argument('--backup', default='/tmp/enderecos_antes_da_faxina.json')
        parser.add_argument('--loja', default='')

    def _planejar_caderno(self, loja):
        """Mesma faxina no caderno do PDV/bot (`UserAddress`), por cliente+loja."""
        from apps.users.models import UserAddress
        qs = UserAddress.objects.order_by('created_at')
        if loja:
            qs = qs.filter(tenant__slug=loja)
        grupos_por_dono = defaultdict(list)
        for a in qs:
            grupos_por_dono[(a.unified_user_id, a.tenant_id)].append(a)
        limpar, apagar, padrao = {}, {}, {}
        for enderecos in grupos_por_dono.values():
            vivos = []
            for a in enderecos:
                rua = CIS.rua_sem_cauda(a.street, numero=a.number, complemento=a.complement,
                                        bairro=a.neighborhood, cidade=a.city, uf=a.state)
                if rua != a.street:
                    limpar[a.id] = (a, rua)
                if not any(CIS.chave_de_texto(v) for v in (rua, a.number, a.complement)):
                    apagar[a.id] = (a, None)
                    continue
                vivos.append((a, rua))
            grupos = defaultdict(list)
            for a, rua in vivos:
                grupos[CIS.chave_do_lugar(rua, a.number, a.complement)].append(a)
            ficam = []
            for grupo in grupos.values():
                grupo.sort(key=lambda x: (x.is_default, x.created_at), reverse=True)
                for s_ in grupo[1:]:
                    apagar[s_.id] = (s_, grupo[0])
                ficam.append(grupo[0])
            padrao.update(_acertar_padrao(enderecos, ficam))
        return {'limpar': limpar, 'apagar': apagar, 'padrao': padrao}

    def _planejar_perfis(self):
        from apps.core.models import UserProfile
        planos = []
        for p in UserProfile.objects.exclude(address='').only('id', 'address'):
            novo = _desempilhar_texto(p.address)
            if novo != p.address:
                planos.append((p, novo))
        return planos

    def handle(self, *args, aplicar=False, backup='', loja='', **kwargs):
        qs = StoreCustomerAddress.objects.select_related('customer', 'customer__store').order_by('created_at')
        if loja:
            qs = qs.filter(customer__store__slug=loja)
        por_cliente = defaultdict(list)
        for a in qs:
            por_cliente[a.customer_id].append(a)

        limpar, apagar, padrao = {}, {}, {}
        for cliente, enderecos in por_cliente.items():
            vivos = []
            for a in enderecos:
                rua = CIS.rua_sem_cauda(a.street, numero=a.number, complemento=a.complement,
                                        bairro=a.neighborhood, cidade=a.city, uf=a.state)
                if rua != a.street:
                    limpar[a.id] = (a, rua)
                if not any(CIS.chave_de_texto(v) for v in (rua, a.number, a.complement)):
                    apagar[a.id] = (a, None)
                    continue
                vivos.append((a, rua))

            grupos = defaultdict(list)
            for a, rua in vivos:
                grupos[CIS.chave_do_lugar(rua, a.number, a.complement)].append(a)
            ficam = []
            for grupo in grupos.values():
                grupo.sort(key=lambda x: (x.is_default, x.created_at), reverse=True)
                dono, saem = grupo[0], grupo[1:]
                for s in saem:
                    apagar[s.id] = (s, dono)
                ficam.append(dono)

            padrao.update(_acertar_padrao(enderecos, ficam))

        caderno = self._planejar_caderno(loja)
        perfis = self._planejar_perfis()

        self.stdout.write(
            f'caderno PDV/bot: {len(caderno["limpar"])} ruas a limpar, {len(caderno["apagar"])} a apagar, '
            f'{len(caderno["padrao"])} padrões | perfis empilhados: {len(perfis)}'
        )
        self.stdout.write(
            f'clientes: {len(por_cliente)} | ruas a limpar: {len(limpar)} | '
            f'endereços a apagar: {len([1 for _, d in apagar.values() if d is None])} vazios + '
            f'{len([1 for _, d in apagar.values() if d is not None])} repetidos | '
            f'padrão a acertar: {len(padrao)}'
        )
        for a, dono in list(apagar.values())[:40]:
            motivo = 'vazio' if dono is None else f'repete {str(dono.id)[:8]}'
            self.stdout.write(f'  apagar {str(a.id)[:8]} ({motivo}): {a.street[:60]!r} {a.number!r}')

        if not aplicar:
            self.stdout.write('simulação — nada gravado (use --aplicar)')
            return

        mexidos = {i: a for i, (a, _) in {**limpar, **apagar, **padrao}.items()}
        foto_caderno = {i: a for i, (a, _) in {**caderno['limpar'], **caderno['apagar'], **caderno['padrao']}.items()}
        with open(backup, 'w') as f:
            json.dump({
                'store_customer_addresses': [_foto(a) for a in mexidos.values()],
                'user_addresses': [_foto_caderno(a) for a in foto_caderno.values()],
                'perfis': [{'id': str(p.id), 'address': p.address} for p, _ in perfis],
            }, f, ensure_ascii=False, indent=1, default=str)

        with transaction.atomic():
            for a, dono in apagar.values():
                if dono is not None:
                    faltando = [c for c in ('neighborhood', 'city', 'state', 'zip_code', 'reference', 'label')
                                if not getattr(dono, c) and getattr(a, c)]
                    for c in faltando:
                        setattr(dono, c, getattr(a, c))
                    if faltando:
                        dono.save(update_fields=faltando)
            StoreCustomerAddress.objects.filter(id__in=list(apagar)).delete()
            for i, (a, rua) in limpar.items():
                if i not in apagar:
                    StoreCustomerAddress.objects.filter(id=i).update(street=rua)
            for i, (a, eh) in padrao.items():
                StoreCustomerAddress.objects.filter(id=i).update(is_default=eh)
            from apps.core.models import UserProfile
            from apps.users.models import UserAddress
            UserAddress.objects.filter(id__in=list(caderno['apagar'])).delete()
            for i, (a, rua) in caderno['limpar'].items():
                if i not in caderno['apagar']:
                    UserAddress.objects.filter(id=i).update(street=rua)
            for i, (a, eh) in caderno['padrao'].items():
                UserAddress.objects.filter(id=i).update(is_default=eh)
            for p, novo in perfis:
                UserProfile.objects.filter(id=p.id).update(address=novo)
        self.stdout.write(f'aplicado — cópia em {backup}')
