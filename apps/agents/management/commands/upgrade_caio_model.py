"""
Management command: upgrade Caio's NVIDIA model to a better instruction-following variant.

Usage:
    python manage.py upgrade_caio_model
    python manage.py upgrade_caio_model --model meta/llama-3.3-70b-instruct
    python manage.py upgrade_caio_model --dry-run
"""
from django.core.management.base import BaseCommand, CommandError

from apps.agents.models import Agent

_RECOMMENDED_MODEL = 'nvidia/llama-3.1-nemotron-70b-instruct'
_ALTERNATIVES = [
    'nvidia/llama-3.1-nemotron-70b-instruct',
    'meta/llama-3.3-70b-instruct',
    'meta/llama-3.1-405b-instruct',
]


class Command(BaseCommand):
    help = 'Upgrade NVIDIA agent model to a better instruction-following variant'

    def add_arguments(self, parser):
        parser.add_argument(
            '--model',
            default=_RECOMMENDED_MODEL,
            help=(
                f'Target NVIDIA NIM model (default: {_RECOMMENDED_MODEL}). '
                f'Alternatives: {", ".join(_ALTERNATIVES)}'
            ),
        )
        parser.add_argument(
            '--agent-id',
            help='Specific agent UUID to update (default: all NVIDIA agents)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without saving',
        )

    def handle(self, *args, **options):
        model_name = options['model']
        dry_run = options['dry_run']
        agent_id = options.get('agent_id')

        qs = Agent.objects.filter(provider=Agent.AgentProvider.NVIDIA)
        if agent_id:
            qs = qs.filter(id=agent_id)

        if not qs.exists():
            self.stdout.write(self.style.WARNING('No NVIDIA agents found.'))
            return

        for agent in qs:
            self.stdout.write(
                f'Agent: {agent.name!r} ({agent.id})\n'
                f'  provider : {agent.provider}\n'
                f'  model    : {agent.model_name!r}  →  {model_name!r}'
            )
            if not dry_run:
                agent.model_name = model_name
                agent.save(update_fields=['model_name'])
                self.stdout.write(self.style.SUCCESS('  ✓ Updated'))
            else:
                self.stdout.write(self.style.WARNING('  (dry-run — no changes saved)'))
