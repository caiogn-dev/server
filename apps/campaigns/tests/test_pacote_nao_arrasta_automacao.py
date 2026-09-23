"""Pegar uma constante não pode arrastar o pacote inteiro.

`apps.automation.mensageiro.janela` importa `JANELA_HORAS` de
`apps.campaigns.services.janela`. Enquanto o `__init__` de campaigns.services
importava `CampaignService` na carga — e ele importa `apps.automation.services`
— esse pedido de constante voltava para um módulo ainda pela metade e o import
estourava.

O estrago não era um erro na cara: três arquivos de teste de automação
paravam de ser COLETADOS pela suíte. Rodando cada um sozinho, passavam. Na
suíte completa, sumiam. Trinta e seis testes que não protegiam nada.

Este teste é o cobrador: importar a constante não pode carregar
`campaign_service`.
"""
import subprocess
import sys


def test_a_constante_da_janela_nao_carrega_o_servico_de_campanha():
    codigo = (
        'import django, os;'
        'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test");'
        'django.setup();'
        'import sys;'
        'from apps.campaigns.services.janela import JANELA_HORAS;'
        'assert "apps.campaigns.services.campaign_service" not in sys.modules, '
        '"pegar a constante arrastou o servico de campanha de volta";'
        'print("ok")'
    )
    r = subprocess.run([sys.executable, '-c', codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]


def test_o_nome_publico_continua_importavel():
    """A saída preguiçosa não pode quebrar quem já importa pelo pacote."""
    from apps.campaigns.services import CampaignService

    assert CampaignService is not None
