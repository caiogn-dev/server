"""
StoreTeamMember model — membros da equipe de uma loja com roles.
"""
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import TenantModel

User = get_user_model()


class StoreTeamMember(TenantModel):
    """
    Membro da equipe de uma loja com role explícito.

    Substitui o campo ManyToMany 'staff' para suportar permissões granulares.
    Herda de TenantModel: UUID pk, tenant FK→Store, created_by, updated_by, timestamps.
    """

    class Role(models.TextChoices):
        OWNER    = 'owner',    'Dono'
        MANAGER  = 'manager',  'Gerente'
        OPERATOR = 'operator', 'Operador'
        VIEWER   = 'viewer',   'Visualizador'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='store_memberships',
        verbose_name='Usuário',
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATOR,
        verbose_name='Role',
        db_index=True,
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name='Ativo',
    )
    invited_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sent_invitations',
        verbose_name='Convidado por',
    )

    class Meta:
        db_table = 'store_team_members'
        verbose_name = 'Membro da Equipe'
        verbose_name_plural = 'Membros da Equipe'
        unique_together = [('tenant', 'user')]
        indexes = [
            models.Index(fields=['tenant', 'role']),
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user} — {self.role} @ {self.tenant}"
