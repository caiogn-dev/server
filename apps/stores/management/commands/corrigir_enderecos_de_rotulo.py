"""Desfaz a catraca do endereço e dá nome aos endereços que são só um ponto.

Dois estragos, os dois nascidos no PDV:

1. **Catraca do rótulo.** `StepEntrega` mandava o rótulo de exibição
   (`rua, número — bairro, cidade-UF`) como endereço do pedido. O servidor
   guarda texto solto em `street`, e o pedido seguinte montava rótulo em cima
   de rótulo. O endereço da Leani (5563992618115) chegou à segunda geração:
   "Secretaria da cidadania e justiça,  — , Palmas-TO,  — , Palmas-TO".

2. **Endereço que é só um ponto.** Link do Maps colado no PDV virou o `street`
   do pedido (CE-2609103109). Link não é endereço para quem lê a comanda.

Os dois caminhos de entrada já foram fechados. Isto limpa o que ficou.

Só relata, a não ser que receba `--aplicar`. Nada é apagado: o texto anterior
vai para `reference` quando não houver nada lá.

    python manage.py corrigir_enderecos_de_rotulo            # relatório
    python manage.py corrigir_enderecos_de_rotulo --aplicar
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.services.customer_identity import CustomerIdentityService
import re

from apps.core.models import UserProfile
from apps.stores.models import StoreCustomerAddress
from apps.stores.services.nome_do_lugar import (
    e_so_um_ponto_no_mapa,
    nomear_se_for_so_um_ponto,
)


# Rastro do template do PDV antigo: separador sem conteúdo entre as vírgulas.
_ASSINATURA_DO_PDV = re.compile(r',\s*—\s*,')


def _formatado(a) -> str:
    linha1 = ', '.join(p for p in [a.street, a.number] if p)
    linha2 = ' - '.join(p for p in [a.complement, a.neighborhood] if p)
    return ', '.join(p for p in [linha1, linha2, a.city, a.state] if p)


class Command(BaseCommand):
    help = 'Desfaz rótulos empilhados no endereço e nomeia endereços que são só um ponto no mapa.'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true', help='Grava. Sem isto, só relata.')

    def handle(self, *args, **opcoes):
        aplicar = opcoes['aplicar']
        mudancas = []

        for a in StoreCustomerAddress.objects.select_related('customer').all():
            rua_antes = a.street or ''
            campos = {}

            if e_so_um_ponto_no_mapa(rua_antes):
                nomeado = nomear_se_for_so_um_ponto({
                    'street': rua_antes, 'number': a.number, 'neighborhood': a.neighborhood,
                    'city': a.city, 'state': a.state, 'zip_code': a.zip_code,
                })
                if (nomeado.get('street') or '') != rua_antes:
                    for campo in ('street', 'number', 'neighborhood', 'city', 'state', 'zip_code'):
                        valor = (nomeado.get(campo) or '').strip()
                        if valor and valor != getattr(a, campo):
                            campos[campo] = valor
                    if not (a.reference or '').strip():
                        campos['reference'] = rua_antes
            else:
                limpa = CustomerIdentityService._tirar_cauda_de_rotulo(rua_antes, a.city, a.state)
                if limpa != rua_antes:
                    campos['street'] = limpa

            if not campos:
                continue

            provisorio = StoreCustomerAddress(
                street=campos.get('street', a.street), number=campos.get('number', a.number),
                complement=a.complement, neighborhood=campos.get('neighborhood', a.neighborhood),
                city=campos.get('city', a.city), state=campos.get('state', a.state),
            )
            campos['formatted'] = _formatado(provisorio)
            mudancas.append((a, rua_antes, campos))

        for a, antes, campos in mudancas:
            self.stdout.write(f'\n  {a.id}  telefone {a.customer.phone}')
            self.stdout.write(f'    antes: {antes!r}')
            self.stdout.write(f'    depois: {campos.get("street", a.street)!r}')
            extras = {k: v for k, v in campos.items() if k not in ('street', 'formatted')}
            if extras:
                self.stdout.write(f'    também: {extras}')

        # `UserProfile.address` guarda o endereço FORMATADO de propósito — a
        # cidade e a UF no fim são o formato, não sujeira. Tirar a cauda de todo
        # perfil apagaria dado correto de 93 clientes.
        #
        # O que é lixo é só a assinatura do template vazio do PDV: ",  — ,"
        # (vírgula, travessão e vírgula sem nada entre eles). Esses, e só esses.
        perfis = []
        for perfil in UserProfile.objects.filter(address__contains='—').iterator():
            if not _ASSINATURA_DO_PDV.search(perfil.address):
                continue
            limpo = CustomerIdentityService._tirar_cauda_de_rotulo(
                perfil.address, perfil.city, perfil.state)
            # A cauda legítima (", cidade, UF") volta: o campo é formatado.
            sufixo = ', '.join(p for p in [perfil.city, perfil.state] if p)
            if sufixo:
                limpo = f'{limpo}, {sufixo}'
            if limpo != perfil.address:
                perfis.append((perfil, perfil.address, limpo))

        for perfil, antes, depois in perfis:
            self.stdout.write(f'\n  perfil {perfil.user_id}  telefone {perfil.phone}')
            self.stdout.write(f'    antes: {antes!r}')
            self.stdout.write(f'    depois: {depois!r}')

        if not mudancas and not perfis:
            self.stdout.write(self.style.SUCCESS('\nNada a corrigir.'))
            return

        if not aplicar:
            self.stdout.write(self.style.WARNING(
                f'\n{len(mudancas)} endereço(s) e {len(perfis)} perfil(is) a corrigir. '
                'Rode com --aplicar para gravar.'))
            return

        with transaction.atomic():
            for a, _antes, campos in mudancas:
                for campo, valor in campos.items():
                    setattr(a, campo, valor)
                a.save(update_fields=list(campos.keys()))
            for perfil, _antes, depois in perfis:
                perfil.address = depois
                perfil.save(update_fields=['address'])
        self.stdout.write(self.style.SUCCESS(
            f'\n{len(mudancas)} endereço(s) e {len(perfis)} perfil(is) corrigido(s).'))
