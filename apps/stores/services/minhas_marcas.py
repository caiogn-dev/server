"""Painel → "Minhas marcas": o dono monta a família de marcas pelo painel.

Grava no metadata as mesmas chaves que `outras_marcas` lê (grupo_de_marcas,
ordem_no_grupo, link_da_marca), só nelas, numa transação com a linha travada:
o metadata guarda outras coisas e não pode ser regravado por inteiro.

Só lojas do MESMO dono entram — mexer no grupo muda o cardápio de várias
lojas, então só o dono edita (equipe da loja não).
"""
from django.db import transaction

from apps.stores.models import Store

CHAVES = ('grupo_de_marcas', 'ordem_no_grupo', 'link_da_marca')


class MarcasErro(Exception):
    pass


def _lojas_do_dono(owner_id):
    return Store.objects.filter(owner_id=owner_id, status='active').order_by('name')


def _link(valor) -> str:
    link = str(valor or '').strip()
    if link and not link.startswith(('https://', 'http://')):
        raise MarcasErro('Link da marca precisa começar com https://')
    return link[:500]


def listar(loja) -> list:
    lojas = list(_lojas_do_dono(loja.owner_id))

    def chave(s):
        meta = s.metadata or {}
        return (0 if meta.get('grupo_de_marcas') else 1, meta.get('ordem_no_grupo') or 0, s.name)

    return [
        {'slug': s.slug, 'nome': s.name, 'logo_url': s.get_logo_url() or '',
         'no_grupo': bool((s.metadata or {}).get('grupo_de_marcas')),
         'link': str((s.metadata or {}).get('link_da_marca') or '')}
        for s in sorted(lojas, key=chave)
    ]


def _avisar_cardapio(slug):
    from apps.stores.services.aviso_ao_cardapio import avisar_que_o_cardapio_mudou
    avisar_que_o_cardapio_mudou(slug)


def salvar(loja, marcas: list) -> list:
    if not isinstance(marcas, list):
        raise MarcasErro('Lista de marcas inválida.')
    do_dono = {s.slug: s for s in _lojas_do_dono(loja.owner_id)}
    pedidas = []
    for item in marcas:
        slug = str((item or {}).get('slug') or '')
        if slug not in do_dono:
            raise MarcasErro('Só entram lojas suas.')
        pedidas.append((slug, bool(item.get('no_grupo')), _link(item.get('link'))))

    existente = next((str((s.metadata or {}).get('grupo_de_marcas'))
                      for s in do_dono.values() if (s.metadata or {}).get('grupo_de_marcas')), '')
    grupo = existente or f'marcas-{loja.owner_id}'
    tocadas = []
    with transaction.atomic():
        travadas = {s.slug: s for s in Store.objects.select_for_update().filter(
            slug__in=[p[0] for p in pedidas], owner_id=loja.owner_id)}
        ordem = 0
        for slug, no_grupo, link in pedidas:
            s = travadas[slug]
            meta = dict(s.metadata or {})
            antes = {k: meta.get(k) for k in CHAVES}
            for k in CHAVES:
                meta.pop(k, None)
            if no_grupo:
                ordem += 1
                meta.update(grupo_de_marcas=grupo, ordem_no_grupo=ordem)
                if link:
                    meta['link_da_marca'] = link
            if {k: meta.get(k) for k in CHAVES} != antes:
                Store.objects.filter(pk=s.pk).update(metadata=meta)
            if no_grupo or antes.get('grupo_de_marcas'):
                tocadas.append(slug)
        # Quem está ou estava no grupo tem a faixa mudada: avisa (sai após o commit).
        for slug in tocadas:
            _avisar_cardapio(slug)
    return listar(loja)
