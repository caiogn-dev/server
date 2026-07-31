# Plano de Relatórios/BI Cardapidex — 2026-07-31

Insumos: benchmark de mercado (Saipos, iFood Portal do Parceiro, Anota AI, OPDV, Repediu, Linx Degust, Blip) + inventário completo de campos do server2 (2 agentes, 31/jul). Objetivo: refinar relatórios do painel usando dados que JÁ existem, com heatmap geográfico, cruzamento de clientes e canal.

## O que o mercado oferece e nós não (gap direto)

| Relatório (referência) | Dá pra fazer hoje? | Fonte de dados |
|---|---|---|
| Heatmap dia×hora de pedidos (padrão-ouro p/ escala de equipe) | ✅ sem migração | `StoreOrder.created_at` |
| Curva ABC de produtos c/ % acumulado (Saipos/Sischef) | ✅ | `StoreOrderItem` agregado |
| Mapa de calor de entrega por bairro (OPDV/Saipos) | ✅ por bairro/CEP; ⚠️ por ponto exato só fatia bot/pin | `delivery_address->>'neighborhood'`, `zip_code`; lat/lng parcial |
| Clientes inativos acionáveis + disparo WhatsApp (Repediu) | ✅ — diferencial: bot já existe | `StoreCustomer.last_order_at` + campanhas |
| Novos vs recorrentes + taxa de recompra (iFood) | ✅ | `StoreCustomer`/`customer_phone` |
| Vendas por forma de pagamento + conciliação (venda×taxa×líquido) | ✅ | `payment_method`, `StorePayment.fee/net_amount` (NUNCA usados) |
| Tempo por etapa / SLA (iFood Painel Logístico) | ✅ | timestamps `confirmed_at`→`delivered_at` (NUNCA usados) |
| Mix por canal bot/web/PDV | ✅ (web = ausência de `source`) | `metadata->>'source'` |
| RFM segmentado (Campeões/Em risco/Perdidos) | ✅ | pedidos por telefone |
| Funil do bot (conversa→carrinho→pago, estilo Blip) | ✅ | `CustomerSession.status` + FK order/conversation |
| Tempo de resposta WhatsApp | ✅ | `Message` inbound→outbound, `Conversation.last_*_message_at` |
| Matriz engenharia de cardápio (Estrela/Abacaxi) | ⚠️ margem aproximada | `StoreProduct.cost_price` EXISTE e nunca foi usado; falta snapshot no item |
| Cohort de retenção mensal | ✅ | pedidos × primeira compra |
| ROI de cupom | ✅ | `coupon_code` string × `discount` |
| Nota média/NPS por período/produto | ✅ | `StoreReview` (1:1 pedido, nunca agregado) |

## Descobertas-chave do inventário

- **Campos ricos dormindo**: `cost_price`, `StorePayment.fee/net_amount`, 10 timestamps de ciclo de vida, `metadata.source`, `delivery_quote.distance_km/zone_name`, `view_count` vs `sold_count`, `StoreCashSession.difference`, `StoreLoyaltyTransaction`, `Campaign.messages_read`.
- **Geo**: lat/lng garantido só em pedido do bot (`order_service._build_delivery_address`) e em `UserAddress` (pin WhatsApp). Checkout web grava se o front mandar, mas `_sanitize_delivery_address_coordinates` pode apagar. Proxy confiável: bairro/CEP + `distance_km` da quote.
- **Fix barato**: `_seed_from_orders` (storefront_views.py:1366) não copia lat/lng do pedido pro `UserAddress` — colunas existem vazias.
- **Infra pronta**: `ReportSchedule`/`GeneratedReport` (relatório agendado por email, xlsx/csv) já existem em apps.automation.

## Roadmap proposto

**Fase 1 — só endpoint novo, zero migração (maior ROI):**
1. Heatmap dia×hora (pedidos e receita).
2. Curva ABC + comparativo período anterior em todos os reports.
3. Vendas por canal (`source`), método de pagamento, delivery vs pickup.
4. Mapa por bairro (ranking + choropleth simples) + anéis de distância (`distance_km`) + overlay zonas (`StoreDeliveryZone.polygon_coordinates`).
5. SLA: tempo médio/p90 por etapa, por zona, por dia.
6. Receita líquida (net_amount) e custo de gateway (fee).
7. RFM + lista de inativos com botão "disparar campanha" (bot existente).
8. Funil bot (`CustomerSession.status`) + tempo de resposta WhatsApp.
9. Nota média (`StoreReview`) no dashboard.

**Fase 2 — migrações pequenas:**
- `StoreOrder.source` CharField indexado (web passa a gravar), `delivery_lat/lng/neighborhood` colunas denormalizadas (preenchidas no checkout + backfill do JSON), `StoreOrderItem.unit_cost` snapshot, `StoreCouponRedemption`.
- Fix `_seed_from_orders` copiar lat/lng.

**Fase 3 — matriz de cardápio (popularidade×margem), cohort visual, conciliação MP completa, relatório de caixa histórico.**

Front (pastita-dash): reutilizar `TimeSeriesChart`+`RankBarList` (base de reports já deployada d66802c); heatmap = grid CSS 7×24; mapa = Leaflet/MapLibre + tiles OSM com bairros agregados (sem custo Google).
