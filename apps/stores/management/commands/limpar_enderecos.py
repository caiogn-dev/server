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


class Command(BaseCommand):
    help = 'Limpa rua empilhada, apaga endereço vazio e junta o mesmo lugar repetido.'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true')
        parser.add_argument('--backup', default='/tmp/enderecos_antes_da_faxina.json')
        parser.add_argument('--loja', default='')

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

            if ficam:
                atuais = [a for a in ficam if a.is_default]
                escolhido = max(atuais or ficam, key=lambda x: x.created_at)
                for a in ficam:
                    if a.is_default != (a is escolhido):
                        padrao[a.id] = (a, a is escolhido)

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
        with open(backup, 'w') as f:
            json.dump([_foto(a) for a in mexidos.values()], f, ensure_ascii=False, indent=1, default=str)

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
        self.stdout.write(f'aplicado — cópia em {backup}')
