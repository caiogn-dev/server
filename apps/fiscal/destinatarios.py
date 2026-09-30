"""Destinatário da nota: validar, guardar e carimbar no pedido."""
import uuid

from .documents import classificar, limpar
from .models import DestinatarioFiscal, FiscalDocument
from .services import CAMPOS_ENDERECO

CAMPOS_DO_ENDERECO = ('street', 'number', 'complement', 'neighborhood', 'city', 'state', 'zip_code')


class DestinatarioInvalido(ValueError):
    """Dado do destinatário que o operador consegue corrigir — vira 400."""


def _texto(valor, limite: int) -> str:
    return str(valor or '').strip()[:limite]


def normalizar(dados: dict, modelo: str = FiscalDocument.Modelo.NFE) -> dict:
    """Devolve o destinatário limpo ou diz o que falta.

    Recusar aqui é o único momento barato: depois da emissão, nota com
    destinatário errado só se cancela (e em 30 minutos).
    """
    if not isinstance(dados, dict):
        raise DestinatarioInvalido('Informe o destinatário da nota.')

    tipo, documento = classificar(str(dados.get('documento') or ''))
    if not tipo:
        raise DestinatarioInvalido('CPF/CNPJ inválido — confira o número.')

    nome = _texto(dados.get('nome'), 255)
    if not nome:
        raise DestinatarioInvalido('Informe o nome ou a razão social do destinatário.')

    bruto = dados.get('endereco') if isinstance(dados.get('endereco'), dict) else {}
    endereco = {
        'street': _texto(bruto.get('street'), 255),
        'number': _texto(bruto.get('number'), 20),
        'complement': _texto(bruto.get('complement'), 120),
        'neighborhood': _texto(bruto.get('neighborhood'), 120),
        'city': _texto(bruto.get('city'), 120),
        'state': _texto(bruto.get('state'), 2).upper(),
        'zip_code': limpar(str(bruto.get('zip_code') or ''))[:8],
    }

    if modelo == FiscalDocument.Modelo.NFE:
        faltando = [rotulo for chave, rotulo in CAMPOS_ENDERECO if not endereco[chave]]
        if faltando:
            raise DestinatarioInvalido(
                f'NF-e exige o endereço completo do destinatário. Faltando: {", ".join(faltando)}.'
            )

    return {
        'documento': documento,
        'nome': nome,
        'inscricao_estadual': limpar(str(dados.get('inscricao_estadual') or ''))[:20],
        'email': _texto(dados.get('email'), 254),
        'telefone': limpar(str(dados.get('telefone') or ''))[:20],
        'endereco': endereco,
    }


def registrar(store, dados: dict, customer=None) -> DestinatarioFiscal:
    """Um cadastro por documento na loja: emitir de novo atualiza, não duplica."""
    campos = {
        'nome': dados['nome'],
        'inscricao_estadual': dados['inscricao_estadual'],
        'email': dados['email'],
        'telefone': dados['telefone'],
        **dados['endereco'],
    }
    if customer is not None:
        campos['customer'] = customer
    destinatario, _ = DestinatarioFiscal.objects.update_or_create(
        store=store, documento=dados['documento'], defaults=campos,
    )
    return destinatario


def como_dict(destinatario: DestinatarioFiscal) -> dict:
    return {
        'id': str(destinatario.id),
        'documento': destinatario.documento,
        'nome': destinatario.nome,
        'inscricao_estadual': destinatario.inscricao_estadual,
        'email': destinatario.email,
        'telefone': destinatario.telefone,
        'customer_id': str(destinatario.customer_id) if destinatario.customer_id else None,
        'endereco': {campo: getattr(destinatario, campo) for campo in CAMPOS_DO_ENDERECO},
    }


def carimbar_no_pedido(order, destinatario: DestinatarioFiscal) -> None:
    """Grava no pedido o retrato do destinatário que vai na nota.

    `cpf_nota` continua sendo a fonte do documento para os dois modelos — o
    retrato acrescenta nome, IE e endereço sem mexer no endereço de entrega.
    """
    retrato = como_dict(destinatario)
    order.metadata = {
        **(order.metadata or {}),
        'cpf_nota': destinatario.documento,
        'destinatario_nota': {
            'destinatario_id': retrato['id'],
            'documento': retrato['documento'],
            'nome': retrato['nome'],
            'inscricao_estadual': retrato['inscricao_estadual'],
            'endereco': retrato['endereco'],
        },
    }
    order.save(update_fields=['metadata', 'updated_at'])


def cliente_do_pedido(order):
    """O StoreCustomer de quem fez o pedido, quando o pedido sabe quem é."""
    from apps.stores.models import StoreCustomer

    referencia = ((order.metadata or {}).get('customer') or {}).get('store_customer_id')
    try:
        referencia = uuid.UUID(str(referencia))
    except (ValueError, TypeError):
        referencia = None
    if referencia:
        cliente = StoreCustomer.objects.filter(store=order.store, pk=referencia).first()
        if cliente:
            return cliente
    if order.customer_id:
        return StoreCustomer.objects.filter(store=order.store, user_id=order.customer_id).first()
    return None
