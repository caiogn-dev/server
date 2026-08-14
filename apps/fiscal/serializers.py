"""Configuração fiscal da loja (store.metadata['fiscal']).

Opt-in por loja: emitir NFC-e exige CNPJ, inscrição estadual, credenciamento
na SEFAZ e certificado — nada disso é global. Uma loja mal configurada só
descobre o problema no primeiro pedido, então a validação é aqui.

Segredos (token do provedor, CSC, senha do certificado) entram por `write_only`
e voltam só como booleano "configurado".
"""
from rest_framework import serializers

from .documents import cnpj_valido, limpar
from .models import FiscalDocument

# campo no metadata -> aparece na resposta como <campo>_configurado
SEGREDOS = ('focus_token', 'csc', 'cert_password')


class ConfigFiscalSerializer(serializers.Serializer):
    habilitado = serializers.BooleanField(required=False)
    provider = serializers.ChoiceField(
        choices=FiscalDocument.Provider.choices, required=False,
    )
    ambiente = serializers.ChoiceField(
        choices=[('homologacao', 'Homologação'), ('producao', 'Produção')], required=False,
    )
    cnpj = serializers.CharField(required=False, allow_blank=True)
    inscricao_estadual = serializers.CharField(required=False, allow_blank=True)
    # UF do emitente: é ela que separa venda no estado (CFOP 5102) de venda
    # interestadual (6102) na NF-e.
    uf = serializers.CharField(required=False, allow_blank=True, max_length=2)
    serie = serializers.CharField(required=False, allow_blank=True)
    csosn = serializers.CharField(required=False, allow_blank=True)
    ncm_padrao = serializers.CharField(required=False, allow_blank=True)
    cfop_padrao = serializers.CharField(required=False, allow_blank=True)

    focus_token = serializers.CharField(required=False, allow_blank=True, write_only=True)
    csc = serializers.CharField(required=False, allow_blank=True, write_only=True)
    csc_id = serializers.CharField(required=False, allow_blank=True)
    cert_password = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_cnpj(self, value):
        numero = limpar(value)
        if numero and not cnpj_valido(numero):
            raise serializers.ValidationError('CNPJ inválido — confira o número.')
        return numero

    def validate_uf(self, value):
        return (value or '').strip().upper()

    def validate(self, attrs):
        """Só valida o conjunto quando a emissão fica ligada: config
        desligada é rascunho, e rascunho pode estar incompleto."""
        atual = self.instance or {}
        final = {**atual, **attrs}
        if not final.get('habilitado'):
            return attrs

        if not final.get('cnpj'):
            raise serializers.ValidationError({'cnpj': 'Informe o CNPJ do emitente antes de ativar.'})

        provider = final.get('provider') or FiscalDocument.Provider.FOCUS
        if provider == FiscalDocument.Provider.FOCUS and not final.get('focus_token'):
            raise serializers.ValidationError(
                {'focus_token': 'Informe o token da Focus NFe antes de ativar a emissão.'}
            )
        if provider == FiscalDocument.Provider.SEFAZ and not (final.get('csc') and final.get('cert_path')):
            raise serializers.ValidationError(
                {'provider': 'Emissão direta SEFAZ exige certificado A1 e CSC — ainda não disponível.'}
            )
        return attrs

    def to_representation(self, config: dict) -> dict:
        config = config or {}
        dados = {
            'habilitado': bool(config.get('habilitado')),
            'provider': config.get('provider') or FiscalDocument.Provider.FOCUS,
            'ambiente': config.get('ambiente') or 'homologacao',
            'cnpj': config.get('cnpj', ''),
            'inscricao_estadual': config.get('inscricao_estadual', ''),
            'uf': config.get('uf', ''),
            'serie': str(config.get('serie', '1')),
            'csosn': config.get('csosn', '102'),
            'ncm_padrao': config.get('ncm_padrao', ''),
            'cfop_padrao': config.get('cfop_padrao', ''),
            'csc_id': config.get('csc_id', ''),
        }
        for campo in SEGREDOS:
            dados[f'{campo}_configurado'] = bool(config.get(campo))
        return dados


def aplicar_config(store, dados: dict) -> dict:
    """Mescla o PATCH na config existente. Segredo ausente no corpo é segredo
    preservado — a tela nunca o mostra, logo nunca pode reenviá-lo."""
    metadata = dict(store.metadata or {})
    config = dict(metadata.get('fiscal') or {})
    for chave, valor in dados.items():
        if chave in SEGREDOS and not valor:
            continue  # não apaga o que a tela não tinha como devolver
        config[chave] = valor
    metadata['fiscal'] = config
    store.metadata = metadata
    store.save(update_fields=['metadata', 'updated_at'])
    return config
