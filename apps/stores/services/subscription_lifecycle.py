"""
Decisão pura do ciclo de vida da assinatura (sem I/O).

Regras:
- Loja isenta (grandfather) nunca transiciona.
- 'active' é mantida.
- 'trialing': se o trial venceu e não há carência marcada → inicia carência
  (grace_until = now + grace_days). Se a carência venceu → suspende.
- 'past_due' (cobrança falhou): se não há relógio de dunning → inicia
  (set_grace_until = now + dunning_days, gravado em dunning_since pela task).
  Se o dunning venceu → suspende.
- 'suspended'/'canceled' são terminais.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass(frozen=True)
class Transition:
    action: str                      # 'none' | 'start_grace' | 'suspend' | 'keep'
    set_grace_until: Optional[datetime] = None


def decide_transition(
    *,
    status: str,
    trial_ends_at: Optional[datetime],
    grace_until: Optional[datetime],
    dunning_since: Optional[datetime],
    now: datetime,
    grace_days: int,
    dunning_days: int,
    billing_exempt: bool,
) -> Transition:
    if billing_exempt:
        return Transition('none')

    if status == 'active':
        return Transition('keep')

    if status in ('suspended', 'canceled'):
        return Transition('none')

    if status == 'trialing':
        if not trial_ends_at or trial_ends_at > now:
            return Transition('none')
        # trial venceu
        if grace_until is None:
            return Transition('start_grace', set_grace_until=now + timedelta(days=grace_days))
        if grace_until <= now:
            return Transition('suspend')
        return Transition('none')

    if status == 'past_due':
        if dunning_since is None:
            return Transition('start_grace', set_grace_until=now + timedelta(days=dunning_days))
        if now - dunning_since >= timedelta(days=dunning_days):
            return Transition('suspend')
        return Transition('none')

    return Transition('none')
