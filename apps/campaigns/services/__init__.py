"""
Campaign services - Unified with Automation.

Note: SchedulerService has been replaced by UnifiedMessagingService from automation app.
Use apps.automation.services.UnifiedMessagingService for scheduled message operations.

`CampaignService` é exportado SOB DEMANDA, não na carga do pacote. Ele importa
`apps.automation.services`, e `apps.automation.mensageiro.janela` importa a
constante `JANELA_HORAS` daqui — pegar uma constante arrastava o pacote inteiro
de volta para `automation.services`, ainda pela metade, e o import estourava.

Efeito real: três arquivos de teste de automação (classificador ligado,
classificador LLM, combo no carrinho) não eram sequer COLETADOS pela suíte
completa. Teste que não roda não protege nada, e ninguém via o erro porque
rodando o arquivo sozinho ele passa.
"""

__all__ = ['CampaignService']


def __getattr__(name):
    """PEP 562: `from apps.campaigns.services import CampaignService` continua
    funcionando, mas o import só acontece quando alguém realmente pede."""
    if name == 'CampaignService':
        from .campaign_service import CampaignService
        return CampaignService
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
