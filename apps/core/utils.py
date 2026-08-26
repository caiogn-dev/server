"""
Core utilities and helper functions.
"""
import hmac
import hashlib
import secrets
from typing import Optional
from django.conf import settings
from cryptography.fernet import Fernet, MultiFernet
import base64


def generate_token(length: int = 32) -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """Hash a token for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify Meta webhook signature."""
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected_signature}", signature)


class TokenEncryption:
    """Encrypt and decrypt sensitive tokens."""

    def __init__(self):
        # Rotação de chave SEM quebrar tokens já gravados (MultiFernet):
        #  - ENCRYPTION_KEY_V2 (chave Fernet REAL, ex.: Fernet.generate_key())
        #    quando definida vira a chave PRIMÁRIA — usada p/ criptografar daqui
        #    pra frente (entropia cheia, sem o truncate/pad fraco).
        #  - A chave legada derivada de ENCRYPTION_KEY/SECRET_KEY continua como
        #    fallback de DEScriptografia, então tokens antigos seguem legíveis.
        # Sem ENCRYPTION_KEY_V2 definida, o comportamento é idêntico ao anterior.
        keys = []
        v2 = getattr(settings, 'ENCRYPTION_KEY_V2', '') or ''
        if v2:
            keys.append(Fernet(v2.encode() if isinstance(v2, str) else v2))
        raw = getattr(settings, 'ENCRYPTION_KEY', '') or settings.SECRET_KEY
        legacy_key = base64.urlsafe_b64encode(raw[:32].encode().ljust(32)[:32])
        keys.append(Fernet(legacy_key))
        self.cipher = MultiFernet(keys)

    def encrypt(self, token: str) -> str:
        """Encrypt a token."""
        return self.cipher.encrypt(token.encode()).decode()

    def decrypt(self, encrypted_token: str) -> str:
        """Decrypt a token."""
        return self.cipher.decrypt(encrypted_token.encode()).decode()


token_encryption = TokenEncryption()


def mask_token(token: str, visible_chars: int = 4) -> str:
    """Mask a token for display purposes."""
    if len(token) <= visible_chars * 2:
        return '*' * len(token)
    return f"{token[:visible_chars]}{'*' * (len(token) - visible_chars * 2)}{token[-visible_chars:]}"


_MIME_EXTENSIONS = {
    'audio/ogg': '.ogg',
    'audio/mpeg': '.mp3',
    'audio/mp4': '.m4a',
    'audio/aac': '.aac',
    'audio/webm': '.weba',
    'audio/wav': '.wav',
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'video/mp4': '.mp4',
    'video/webm': '.webm',
    'video/3gpp': '.3gp',
    'application/pdf': '.pdf',
    'application/msword': '.doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
}


def mime_to_extension(mime_type: str) -> str:
    """Return file extension for a MIME type, stripping codec parameters.
    Falls back to mimetypes module if not in the hardcoded map.
    """
    import mimetypes
    base = (mime_type or '').split(';')[0].strip().lower()
    if base in _MIME_EXTENSIONS:
        return _MIME_EXTENSIONS[base]
    return mimetypes.guess_extension(base) or ''


def build_absolute_media_url(url: str) -> str:
    """Ensure media URL is absolute using BACKEND_URL when needed."""
    if not url:
        return ''
    if url.startswith('http://') or url.startswith('https://'):
        return url
    base = settings.BACKEND_URL.rstrip('/')
    if not url.startswith('/'):
        url = f'/{url}'
    return f"{base}{url}"


def _parece_brasileiro_local(digitos: str) -> bool:
    """True quando o número é um telefone BR SEM o DDI (DDD + assinante).

    Rede de segurança para quando o libphonenumber não reconhece o número —
    caso real e comum: o `wa_id` do WhatsApp entrega celular brasileiro SEM o
    nono dígito (`556392429380`), formato que a biblioteca considera inválido
    porque não existe mais na numeração oficial. Ele existe no nosso banco.

    - 11 dígitos: DDD + 9XXXXXXXX — celular sempre tem 9 na terceira posição.
    - 10 dígitos: DDD + XXXXXXXX — fixo começa entre 2 e 5.

    A terceira posição é o que separa um celular brasileiro de um número
    estrangeiro completo do mesmo tamanho: `34647520824` (Espanha) e
    `15554044637` (EUA) também têm 11 dígitos, mas não têm o 9.
    """
    if len(digitos) not in (10, 11):
        return False
    ddd = digitos[:2]
    if not ('11' <= ddd <= '99'):
        return False
    if len(digitos) == 11:
        return digitos[2] == '9'
    return digitos[2] in '2345'


def _parse_telefone(valor: str, digitos: str):
    """Interpreta o telefone com libphonenumber. Devolve o objeto ou None.

    A ordem das três tentativas é o coração da regra e não é arbitrária:

    1. **Veio com `+`** → o DDI é uma AFIRMAÇÃO do cliente, não um palpite.
       `+34 647 52 08 24` é espanhol porque ela disse que é.
    2. **Sem `+`, tenta como brasileiro** → é o caso de 99% dos pedidos:
       `63992429380` digitado no checkout de Palmas.
    3. **Sem `+` e não é BR válido** → o DDI já está embutido nos dígitos.
       É assim que o `wa_id` do WhatsApp chega: `34647520824`, sem `+`.

    Inverter 2 e 3 quebraria o Brasil: `6332151234` (fixo de Palmas) também
    é um número internacional sintaticamente plausível.
    """
    import phonenumbers

    tentativas = []
    if valor.strip().startswith('+'):
        tentativas.append(('+' + digitos, None))
    else:
        tentativas.append((digitos, 'BR'))
        tentativas.append(('+' + digitos, None))

    for texto, regiao in tentativas:
        try:
            numero = phonenumbers.parse(texto, regiao)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(numero):
            return numero
    return None


def normalize_phone_number(phone: str, default_region: str = 'BR') -> str:
    """Normalize phone number to E.164 format (sem o '+').

    Fonte única de verdade do telefone no sistema. Usa o libphonenumber, que
    conhece DDI, DDD e regra de numeração de TODO país — então um cliente novo
    de qualquer lugar passa a funcionar sem ninguém escrever código por país.

    A regra antiga era de tamanho ("sem 55 e até 11 dígitos → gruda 55") e
    transformava número estrangeiro completo em brasileiro inexistente: a
    conversa da Layane (wa_id `34647520824`, Espanha) virou `5534647520824` e
    toda resposta do inbox falhou com 131026 enquanto ela tentava fazer um
    pedido.

    Quando o libphonenumber não reconhece (celular BR legado sem o nono
    dígito, número de teste), cai na heurística — que preserva o dígito a
    dígito em vez de inventar um DDI.
    """
    valor = str(phone or '')
    digitos = ''.join(filter(str.isdigit, valor))
    if not digitos:
        return ''

    import phonenumbers

    numero = _parse_telefone(valor, digitos)
    if numero is not None:
        return phonenumbers.format_number(
            numero, phonenumbers.PhoneNumberFormat.E164
        ).lstrip('+')

    if not digitos.startswith('55') and _parece_brasileiro_local(digitos):
        digitos = '55' + digitos
    return digitos


def format_phone_for_display(phone: str) -> str:
    """Format phone number for display.

    Brasileiro sai no formato que o dono do painel lê sem pensar —
    `+55 (63) 99250-9193`. Estrangeiro sai no formato do PRÓPRIO país: exibir
    `+34 647520824` como `(34) 64752-0824` faz o atendente ligar para
    Uberlândia achando que é DDD.
    """
    normalizado = normalize_phone_number(phone)
    if not normalizado:
        return ''

    import phonenumbers

    if not normalizado.startswith('55'):
        try:
            numero = phonenumbers.parse('+' + normalizado, None)
            if phonenumbers.is_valid_number(numero):
                return phonenumbers.format_number(
                    numero, phonenumbers.PhoneNumberFormat.INTERNATIONAL
                )
        except phonenumbers.NumberParseException:
            pass
        return '+' + normalizado

    if len(normalizado) == 13:
        return f"+{normalizado[:2]} ({normalizado[2:4]}) {normalizado[4:9]}-{normalizado[9:]}"
    if len(normalizado) == 12:
        return f"+{normalizado[:2]} ({normalizado[2:4]}) {normalizado[4:8]}-{normalizado[8:]}"
    return normalizado


def generate_idempotency_key(*args) -> str:
    """Generate an idempotency key from arguments."""
    data = ':'.join(str(arg) for arg in args)
    return hashlib.sha256(data.encode()).hexdigest()


def validate_cpf(cpf: str) -> bool:
    """
    Validate a Brazilian CPF number using the official algorithm.
    
    The CPF consists of 11 digits: 9 base digits + 2 verification digits.
    The verification digits are calculated using modulo 11.
    
    Args:
        cpf: CPF string (can contain formatting characters)
        
    Returns:
        True if valid, False otherwise
    """
    # Remove non-digit characters
    cpf = ''.join(filter(str.isdigit, str(cpf or '')))
    
    # Must have exactly 11 digits
    if len(cpf) != 11:
        return False
    
    # Reject known invalid CPFs (all same digits)
    if cpf == cpf[0] * 11:
        return False
    
    # Calculate first verification digit
    total = 0
    for i in range(9):
        total += int(cpf[i]) * (10 - i)
    
    remainder = total % 11
    first_digit = 0 if remainder < 2 else 11 - remainder
    
    if int(cpf[9]) != first_digit:
        return False
    
    # Calculate second verification digit
    total = 0
    for i in range(10):
        total += int(cpf[i]) * (11 - i)
    
    remainder = total % 11
    second_digit = 0 if remainder < 2 else 11 - remainder
    
    if int(cpf[10]) != second_digit:
        return False
    
    return True


def format_cpf(cpf: str) -> str:
    """
    Format a CPF number for display.
    
    Args:
        cpf: CPF string (digits only or formatted)
        
    Returns:
        Formatted CPF (XXX.XXX.XXX-XX) or original if invalid length
    """
    cpf = ''.join(filter(str.isdigit, str(cpf or '')))
    
    if len(cpf) != 11:
        return cpf
    
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def clean_cpf(cpf: str) -> str:
    """
    Remove formatting from CPF, returning only digits.
    
    Args:
        cpf: CPF string (formatted or not)
        
    Returns:
        CPF with only digits
    """
    return ''.join(filter(str.isdigit, str(cpf or '')))


def inicio_do_dia():
    """Instante em que o dia de HOJE começou, no fuso da loja.

    `timezone.now().replace(hour=0, ...)` parece certo e não é: `now()` devolve
    UTC, então a meia-noite resultante é 00:00 UTC — 21:00 de Brasília do dia
    ANTERIOR. Efeito prático no painel: todo dia às 21h o dia "virava" em UTC e
    o card "Receita hoje" descartava o faturamento das 00h às 21h — justamente
    o pico do delivery. Antes das 21h o erro era o oposto: colava as vendas do
    fim da noite anterior no dia de hoje.

    Converta para o fuso local ANTES de zerar a hora.
    """
    from django.utils import timezone

    return timezone.localtime(timezone.now()).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def phone_variants(phone: str) -> list:
    """Todas as formas em que ESTE MESMO telefone aparece no sistema.

    O WhatsApp entrega o `wa_id` de celular brasileiro SEM o nono dígito
    (`556392618115`, 12 dígitos), enquanto formulário do site, painel e PDV
    gravam COM ele (`5563992618115`, 13). São a mesma pessoa e o sistema tratava
    como duas — o cliente ganhava uma conversa fantasma sem histórico para onde
    iam as notificações do pedido, e a busca de pedido por telefone no bot nunca
    casava ("Não encontrei pedidos recentes" logo após confirmar o pedido).

    Devolve as variantes com e sem DDI 55, com e sem o nono dígito, e cada uma
    também na forma `+55...`. Use em QUALQUER lookup por telefone
    (`filter(campo__in=phone_variants(...))`), nunca compare telefone por
    igualdade direta.
    """
    digitos = ''.join(filter(str.isdigit, str(phone or '')))
    if not digitos:
        return []

    nucleos = {digitos, normalize_phone_number(digitos)}

    def _alterna_nono(valor: str) -> set:
        """Gera o par com/sem o nono dígito para celular brasileiro."""
        saida = set()
        if valor.startswith('55') and len(valor) > 11:
            local = valor[2:]
            prefixo = '55'
        elif _parece_brasileiro_local(valor):
            local = valor
            prefixo = ''
        else:
            # O nono dígito é regra da ANATEL. Aplicá-la a um número
            # estrangeiro inventa telefones que não existem — e um lookup por
            # `campo__in=phone_variants(...)` pode casar com o cliente ERRADO.
            return saida
        # local = DDD (2) + assinante (8 ou 9)
        if len(local) == 11 and local[2] == '9':
            saida.add(prefixo + local[:2] + local[3:])      # remove o 9
        elif len(local) == 10:
            saida.add(prefixo + local[:2] + '9' + local[2:])  # adiciona o 9
        return saida

    for valor in list(nucleos):
        nucleos |= _alterna_nono(valor)

    # Cada núcleo também vale sem o DDI e com o prefixo '+'.
    completo = set(nucleos)
    for valor in nucleos:
        if valor.startswith('55') and len(valor) > 11:
            completo.add(valor[2:])
    for valor in list(completo):
        completo.add(f'+{valor}')

    return [v for v in completo if v]
