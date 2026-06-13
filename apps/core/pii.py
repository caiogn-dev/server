"""Máscara de PII para uso em logs (LGPD art. 46 — não logar dado pessoal em claro)."""


def mask_phone(phone: str) -> str:
    s = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not s:
        return ""
    if len(s) <= 6:
        return "*" * len(s)
    return f"{s[:2]}{'*' * (len(s) - 6)}{s[-4:]}"


def mask_email(email: str) -> str:
    email = str(email or "")
    if "@" not in email:
        return "***" if email else ""
    local, domain = email.split("@", 1)
    head = local[:1] if local else ""
    return f"{head}***@{domain}"


def mask_cpf(cpf: str) -> str:
    s = "".join(ch for ch in str(cpf or "") if ch.isdigit())
    if len(s) < 4:
        return "***"
    return f"***.***.**{s[-3]}-{s[-2:]}"


_MASKERS = {"phone": mask_phone, "email": mask_email, "cpf": mask_cpf, "document": mask_cpf}


def mask_pii(data: dict) -> dict:
    """Mascara chaves conhecidas de PII num dict (para log). Nome é removido."""
    out = {}
    for k, v in (data or {}).items():
        key = k.lower()
        if key in _MASKERS:
            out[k] = _MASKERS[key](v)
        elif key in ("name", "customer_name", "full_name"):
            out[k] = "***"
        else:
            out[k] = v
    return out
