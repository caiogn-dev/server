# Link na Bio — Design (2026-07-28)

Feature do Cardapidex: cada loja ganha uma página pública tipo Linktree em
`bio.cardapidex.com.br/<slug>`, pra colocar na bio do Instagram. Nasce pronta
(links automáticos derivados do que o Store já tem) e é personalizável no dash
(links customizados — ex.: pesquisa de satisfação, iFood). Cliques são contados
no backend e viram card no dash.

**Decisões fechadas com o usuário:**
- Feature do ecossistema Cardapidex (não SaaS separado).
- Conteúdo auto-gerado + editável no dash.
- URL: `bio.cardapidex.com.br/<slug>` (vhost/DNS novo apontando pro
  cardapidex-web de produção). Arquitetura host-agnostic pra aceitar um domínio
  curto no futuro (ex.: `cardp.li`) só com mais um vhost/DNS, zero código.
- Gate por plano: página básica automática em todos os planos (com rodapé
  Cardapidex = mídia grátis); links customizados + analytics + remover branding
  são Pro/Premium.
- Analytics: contador simples no backend via redirect (sem tabela de eventos).
- Implementação: subagent-driven (superpowers:subagent-driven-development).

## 1. Dados (server2)

- **Model `StoreBioLink`** (app `stores`): `store` FK, `title` (char),
  `url` (URLField), `icon` (char curto, emoji), `sort_order` (int),
  `is_active` (bool), timestamps. Somente links **customizados**.
- **Links automáticos** não são linhas no banco. O serializer gera na hora a
  partir do Store: Cardápio (URL do storefront), WhatsApp (`wa.me` do número da
  loja), Endereço (link Google Maps), Instagram (se cadastrado). Cada um tem uma
  key estável: `auto:menu`, `auto:whatsapp`, `auto:maps`, `auto:instagram`.
- **Config da página** em `store.metadata.bio_settings` (mesmo padrão do
  meta-tracking): toggles por link automático (default: todos on) e `headline`
  (texto curto sob o logo).
- **Model `BioClickStat`** (app `stores`): `store` FK, `date`, `link_key`
  (char), `clicks` (int). Unique together (store, date, link_key). Incremento
  atômico via `F()` + `get_or_create`. Views da página usam key `page:view`.
  Sem tabela de eventos individuais — só agregado diário.

## 2. API (server2)

### Público (sem auth)
- `GET /api/public/stores/<slug>/bio/` → payload da página:
  branding (nome, logo, cores — campos que já existem no PublicStoreSerializer),
  `headline`, lista **ordenada** de links (automáticos habilitados + customizados
  ativos; automáticos primeiro, customizados por `sort_order`), cada link com
  `{key, title, icon, href}` onde `href` é a URL de redirect (abaixo), e flag
  `show_branding` (true quando o plano NÃO tem `bio_custom_links`).
  Incrementa `page:view` no `BioClickStat` a cada GET.
- `GET /api/public/bio/<slug>/r/<key>/` → resolve a key server-side,
  incrementa o contador e responde **302 pra URL que está no banco/derivada do
  Store**. Sem parâmetro de destino na query → sem open redirect.
  Key inválida/desativada/deletada → 302 pra própria página bio (não quebra).

### Dash (auth, owner da loja)
- CRUD `/.../bio-links/` (list, create, update, delete) + action de reorder
  (recebe lista de ids na nova ordem).
- `GET /.../bio-stats/?days=30` → views da página + cliques por link_key por
  dia (série) e totais.
- `PATCH` das `bio_settings` (toggles + headline) via endpoint de metadata já
  existente ou action dedicada — seguir o padrão do meta-tracking.

### Gates de plano (PLAN_CATALOG + plan_allows, padrão do coupon_banner)
- `bio_custom_links` (Pro+): criar/editar link custom sem plano → 403 com
  mensagem de upgrade. **Downgrade**: links custom param de aparecer na página
  pública mas NÃO são deletados — voltam se re-assinar.
- `bio_analytics` (Pro+): `bio-stats` responde 403 sem o plano.
- Página básica (links automáticos) sai em **todos** os planos.
- Lojas `billing_exempt` passam em tudo (comportamento já existente do
  `plan_allows`).

## 3. Página pública (cardapidex-web)

- Rota `/bio/[slug]` com SSR (getServerSideProps chamando o endpoint público).
- `middleware` reescreve por host: requests com host `bio.cardapidex.com.br`
  e path `/<slug>` → `/bio/<slug>`. Host-agnostic: qualquer host configurado
  na lista de hosts-bio sofre o mesmo rewrite (preparado pro domínio curto).
- Visual: tema dinâmico da loja (cores da API — sistema já existente), logo,
  headline, botões empilhados mobile-first, rodapé "feito com Cardapidex"
  (link pro site institucional) quando `show_branding`.
- Todo botão aponta pro endpoint de redirect do server2 (é ele que conta).
- Clarity + Meta Pixel da loja montam na página (componentes `Clarity.jsx` e
  `MetaPixel.jsx` já existem no app; mesmo gate LGPD).
- Slug inexistente ou loja inativa → 404.
- Infra: 1 registro DNS `bio.cardapidex.com.br` + 1 vhost nginx apontando pro
  mesmo Next de produção.

## 4. Dash (pastita-dash)

Página nova "Link na Bio" (navbar via `buildNavSections`, seção de
marketing/configurações):
- URL da página com botão copiar.
- Preview (iframe ou mock estilizado).
- Toggles dos links automáticos + campo headline.
- CRUD dos links customizados (título + URL + emoji) com reorder
  (drag ou setas ↑↓ — o que for mais simples com os componentes existentes).
- Card de cliques: views da página + cliques por link, últimos 30 dias
  (reusar TimeSeriesChart/RankBarList dos reports).
- Gate UI: sem `bio_custom_links`/`bio_analytics` → seção bloqueada com CTA de
  upgrade, mesmo padrão do banner de cupom (gamificação Fase 1).

## 5. Erros e casos-borda

- Slug inexistente / loja inativa → 404 na página pública.
- Clique em link deletado/desativado → 302 pra página bio.
- Downgrade de plano → customs somem da página pública, dados preservados.
- Redirect nunca aceita destino vindo do cliente (anti open-redirect).
- Contadores: incremento atômico (F()), sem race em cliques concorrentes.

## 6. Testes (TDD)

- **server2**: payload público (auto+custom, ordem, headline, show_branding
  por plano), toggles de bio_settings respeitados, 403 dos gates
  (`bio_custom_links` no create, `bio_analytics` no stats), increment de clique
  e de view, redirect 302 correto + fallback de key inválida, downgrade esconde
  customs sem deletar, non-owner 404 no CRUD (padrão IDOR dos testes atuais).
- **cardapidex-web**: render da página (tema, botões, rodapé condicional),
  middleware de host rewrite.
- **pastita-dash**: página nova renderiza, CRUD, gate UI.
- Baselines atuais: server2 1277 pass/45 falhas conhecidas; dash 524; web 142.
  Zero regressão vs baseline.

## 7. Deploy (ordem)

1. server2 (migrations + API) — docker cp nos 3 containers + docker commit,
   padrão vigente.
2. cardapidex-web (rota + middleware) + DNS `bio.cardapidex.com.br` + vhost
   nginx.
3. pastita-dash (push main → Vercel).
4. Verificação ao vivo: abrir bio da Cê Saladas, clicar, conferir contador no
   dash.
