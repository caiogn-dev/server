"""Validação de CPF/CNPJ — dígito verificador, não só formato.

Existe porque a SEFAZ rejeita a NFC-e inteira quando o documento do
destinatário não fecha (rejeição 237). Descobrir isso na hora da emissão é
tarde: a venda já aconteceu. Validamos onde o número é digitado.
"""
import re

__all__ = ['limpar', 'cpf_valido', 'cnpj_valido', 'classificar']


def limpar(valor: str) -> str:
    """Só os dígitos — a SEFAZ não aceita máscara."""
    return re.sub(r'\D', '', valor or '')


def _digito(base: str, pesos: list[int]) -> str:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return '0' if resto < 2 else str(11 - resto)


def cpf_valido(valor: str) -> bool:
    cpf = limpar(valor)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    d1 = _digito(cpf[:9], list(range(10, 1, -1)))
    d2 = _digito(cpf[:9] + d1, list(range(11, 1, -1)))
    return cpf[9:] == d1 + d2


def cnpj_valido(valor: str) -> bool:
    cnpj = limpar(valor)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = _digito(cnpj[:12], pesos1)
    d2 = _digito(cnpj[:12] + d1, pesos2)
    return cnpj[12:] == d1 + d2


def classificar(valor: str) -> tuple[str, str]:
    """('cpf'|'cnpj'|'', numero_limpo). Tipo vazio = não use este documento."""
    numero = limpar(valor)
    if cpf_valido(numero):
        return 'cpf', numero
    if cnpj_valido(numero):
        return 'cnpj', numero
    return '', numero
