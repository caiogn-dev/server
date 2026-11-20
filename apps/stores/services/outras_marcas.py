"""Marcas do mesmo grupo, para a faixa "Conheça nossas outras marcas" do cardápio.

Configuração no metadata da loja:
- `grupo_de_marcas`: chave do grupo (mesma chave = mesma família);
- `ordem_no_grupo`: posição na faixa;
- `link_da_marca`: opcional, troca o cardápio por um link externo
  (ex.: Agrião aponta para o Prefiro enquanto o cardápio dela não está pronto).

Só entram lojas ativas do MESMO dono: a chave sozinha não pode puxar loja alheia.
"""
from apps.stores.models import Store


def _link_externo(loja):
    link = str((loja.metadata or {}).get('link_da_marca') or '').strip()
    return link if link.startswith(('https://', 'http://')) else ''


def outras_marcas(loja):
    grupo = (loja.metadata or {}).get('grupo_de_marcas')
    if not grupo or not loja.owner_id:
        return []
    irmas = (
        Store.objects
        .filter(owner_id=loja.owner_id, status='active', metadata__grupo_de_marcas=grupo)
        .exclude(pk=loja.pk)
    )
    irmas = sorted(irmas, key=lambda s: ((s.metadata or {}).get('ordem_no_grupo') or 0, s.name))
    return [
        {
            'slug': s.slug,
            'nome': s.name,
            'logo_url': s.get_logo_url() or '',
            'url': _link_externo(s) or f'/{s.slug}',
        }
        for s in irmas
    ]
