# Google Maps Migration Architecture

Data: 2026-04-17
Escopo: backend Django `server2`, storefront público, checkout, validação de entrega, WhatsApp e futura integração com `toca-delivery`

## 1. Resumo executivo

O projeto já tem uma camada funcional de mapas, mas ela está semanticamente acoplada ao HERE em nome, contrato interno e comportamento operacional. A mudança para Google Maps não deve ser tratada como troca pontual de provider; ela precisa ser feita como substituição da camada geoespacial canônica do domínio de entrega.

O objetivo correto é:

- manter o contrato público atual para frontend e canais conversacionais;
- substituir o provider de geocoding, reverse geocoding, rota e autocomplete por Google;
- preservar `polyline` no backend para o mapa gerado no frontend;
- reduzir erros de endereço incorreto no checkout;
- preparar o backend para interoperar com `toca-delivery` como sistema terceiro de despacho/logística.

Se isso for feito direto em cima do código atual, sem abstração, o time troca um acoplamento por outro. A abordagem recomendada é introduzir uma interface de provider geoespacial, colocar Google como provider primário, manter compatibilidade de payload e isolar regras de negócio do detalhe da API externa.

## 2. Contexto de negócio

Hoje o mapa não serve só para desenhar rota. Ele influencia decisão comercial e operacional:

- taxa de entrega;
- aceitação ou recusa de pedidos fora da área;
- estimativa de tempo;
- qualidade do endereço salvo em pedido, sessão e atendimento;
- experiência do cliente no checkout;
- automação via WhatsApp;
- futura integração com plataforma de entregas.

Erro de geocodificação não é bug cosmético. Ele gera:

- endereço salvo errado;
- taxa incorreta;
- pedido aceito fora da cobertura;
- custo operacional maior;
- atrito no atendimento humano;
- baixa confiança do cliente no mapa exibido.

Portanto, a migração precisa ser tratada como iniciativa de confiabilidade operacional, não apenas de frontend ou de infraestrutura.

## 3. Achados da análise

### 3.1 Onde o backend atual está acoplado ao HERE

Os pontos centrais encontrados no `server2`:

- [apps/stores/services/here_maps_service.py](/home/graco/WORK/server2/apps/stores/services/here_maps_service.py:1)
- [apps/stores/api/maps_views.py](/home/graco/WORK/server2/apps/stores/api/maps_views.py:1)
- [apps/stores/api/views/storefront_views.py](/home/graco/WORK/server2/apps/stores/api/views/storefront_views.py:676)
- [apps/whatsapp/services/order_service.py](/home/graco/WORK/server2/apps/whatsapp/services/order_service.py:185)
- [apps/whatsapp/intents/handlers.py](/home/graco/WORK/server2/apps/whatsapp/intents/handlers.py:359)
- [config/settings/base.py](/home/graco/WORK/server2/config/settings/base.py:370)

Capacidades que hoje dependem do HERE:

- `geocode`
- `reverse_geocode`
- `calculate_route`
- `autosuggest`
- `get_isoline`
- `get_delivery_zones_isolines`
- `validate_delivery_address`
- `calculate_delivery_fee`

Impacto real:

- o nome do serviço (`HereMapsService`) vazou para todo o domínio;
- testes e patches mockam diretamente `apps.stores.services.here_maps_service`;
- o contrato de componentes de endereço traz observações específicas do HERE;
- fallback de rota por haversine existe e precisa continuar;
- há heurística local importante para Palmas e zonas fixas que não pode ser perdida.

### 3.2 Dependência funcional no checkout e atendimento

O fluxo de checkout usa `geocode` quando recebe endereço/CEP sem coordenadas e depois usa rota real para calcular taxa. Isso acontece em [apps/stores/api/views/storefront_views.py](/home/graco/WORK/server2/apps/stores/api/views/storefront_views.py:676).

O atendimento conversacional também depende da camada geográfica:

- geocodificação de endereço digitado;
- reverse geocode de localização enviada;
- preenchimento estruturado do `delivery_address`.

Hoje o serviço de pedido do WhatsApp tem mapeamento explícito de chaves do HERE em [apps/whatsapp/services/order_service.py](/home/graco/WORK/server2/apps/whatsapp/services/order_service.py:185). Esse ponto vai quebrar semanticamente se a troca for feita sem normalização de payload.

### 3.3 Situação no `toca-delivery`

O projeto correto encontrado foi `/opt/toca-delivery`.

Foi confirmado, sem expor segredo, que o `.env.prod` desse projeto já usa:

- `GOOGLE_MAPS_KEY`
- `NEXT_PUBLIC_GOOGLE_MAPS_KEY`
- `GOOGLE_MAPS_ANDROID_API_KEY`

Também foi confirmado que o `toca-delivery` já persiste no backend:

- `route_polyline`
- `route_distance_meters`
- `route_duration_seconds`
- `active_route_polyline`
- `active_route_distance_meters`
- `active_route_duration_seconds`

Referências principais:

- `/opt/toca-delivery/services/api/app/modules/corridas/service.py`
- `/opt/toca-delivery/services/api/app/modules/corridas/router.py`

Padrão encontrado no `toca-delivery`:

- Google Geocoding para endereço -> coordenadas;
- Google Geocoding reverso para coordenadas -> endereço estruturado;
- Google Directions para rota e `overview_polyline`;
- Google Distance Matrix para distância operacional;
- frontend web e mobile já desenhando polyline Google nativamente.

Conclusão prática: o `toca-delivery` já valida o desenho-alvo que queremos para este projeto.

## 4. Diagnóstico arquitetural

### 4.1 Problema estrutural atual

O projeto mistura três camadas que deveriam estar separadas:

- integração com provider externo;
- normalização geoespacial do domínio;
- regra de negócio de entrega.

Exemplos:

- `HereMapsService` calcula rota e também aplica regra de taxa;
- payload de API externa influencia nomes internos de campos;
- o domínio de entrega depende do nome do provider.

### 4.2 Arquitetura alvo

Criar uma camada canônica de geosserviços:

- `GeoProvider`: interface abstrata
- `GoogleMapsProvider`: implementação primária
- `FallbackGeoProvider` opcional: haversine + comportamento degradado
- `geo_service`: fachada estável consumida pelo resto do sistema

Separação recomendada:

- provider: chama API externa e traduz resposta bruta;
- normalizer: converte resposta para contrato interno canônico;
- domain service: aplica validação, fee, zona e mensagens;
- API views: apenas orquestram request/response.

## 5. Contrato canônico recomendado

O contrato interno não deve depender do Google nem do HERE.

### 5.1 Geocode

Resposta canônica:

```python
{
    "lat": float,
    "lng": float,
    "formatted_address": str,
    "place_id": str | None,
    "address_components": {
        "street": str,
        "number": str,
        "neighborhood": str,
        "city": str,
        "state": str,
        "state_code": str,
        "zip_code": str,
        "country": str,
        "country_code": str,
    },
    "provider": "google",
}
```

### 5.2 Reverse geocode

Mesma estrutura de `address_components`, com `formatted_address`, `lat`, `lng` quando útil.

### 5.3 Route

Resposta canônica:

```python
{
    "distance_km": float,
    "distance_meters": int,
    "duration_minutes": float,
    "duration_seconds": int,
    "polyline": str | None,
    "departure": dict,
    "arrival": dict,
    "provider": "google",
    "fallback": bool,
}
```

### 5.4 Autosuggest

Resposta canônica:

```python
{
    "title": str,
    "subtitle": str | None,
    "lat": float | None,
    "lng": float | None,
    "place_id": str | None,
}
```

## 6. Estratégia recomendada de migração

### Fase 0. Congelamento de contrato

Antes de alterar provider:

- preservar endpoints públicos atuais;
- preservar nomes de campos já consumidos;
- registrar payloads reais de sucesso e erro;
- mapear todos os testes que mockam `HereMapsService`.

Resultado esperado:

- nenhum frontend precisa mudar para a primeira entrega;
- a migração acontece por trás do contrato existente.

### Fase 1. Introdução da abstração

Criar novos módulos, sem remover o legado ainda:

- `apps/stores/services/geo/contract.py`
- `apps/stores/services/geo/google_provider.py`
- `apps/stores/services/geo/service.py`
- `apps/stores/services/geo/normalizers.py`

Diretriz:

- `here_maps_service.py` vira casca de compatibilidade temporária ou é substituído por um alias para `geo_service`;
- código consumidor deixa de importar `HereMapsService` diretamente.

### Fase 2. Implementação Google

Implementar no backend:

- geocode via Google Geocoding API;
- reverse geocode via Google Geocoding API;
- route via Google Directions API;
- autosuggest via Google Places Autocomplete API;
- fallback de rota por haversine quando a API falhar.

Observação importante:

- o `polyline` do Google (`overview_polyline.points`) atende perfeitamente o requisito de renderização em frontend web/mobile;
- o backend deve continuar sendo a fonte de verdade da polyline quando o mapa precisar refletir cálculo operacional.

### Fase 3. Normalização de componentes de endereço

Esse é o ponto crítico para não quebrar checkout e WhatsApp.

A camada nova deve entregar sempre:

- `street`
- `number`
- `neighborhood`
- `city`
- `state`
- `state_code`
- `zip_code`
- `country`
- `country_code`

Depois disso, adaptar [apps/whatsapp/services/order_service.py](/home/graco/WORK/server2/apps/whatsapp/services/order_service.py:185) para parar de conhecer variantes do HERE.

### Fase 4. Isolines e zonas de entrega

Google Maps não oferece um equivalente direto ao `HERE Isoline` no mesmo modelo.

Decisão arquitetural recomendada:

- não migrar isolines 1:1 agora;
- tratar `delivery_zones` do produto como política de negócio, não como dependência do provider;
- curto prazo: manter validação por rota/distância/tempo;
- médio prazo: substituir isolines por polígonos próprios persistidos no banco ou integração com engine geoespacial específica.

Conclusão objetiva:

- geocode, reverse, route e autosuggest podem migrar imediatamente para Google;
- isoline deve ser desacoplado da estratégia principal de cobertura.

### Fase 5. Feature flag e rollout seguro

Adicionar configuração:

- `GEO_PROVIDER=google`
- `GOOGLE_MAPS_KEY=...`
- opcional: `GOOGLE_PLACES_KEY=...` se quiser separar billing/permissões depois
- legado temporário: `HERE_API_KEY` mantido apenas até remoção completa

Rollout recomendado:

1. ambiente local/staging com Google primário;
2. produção com shadow testing e logs comparativos;
3. ativação por feature flag;
4. remoção definitiva do HERE após estabilização.

## 7. Uso da chave do `toca-delivery`

É viável usar a mesma chave do `toca-delivery` neste projeto, desde que isso seja feito no ambiente de deploy, não hardcoded em código nem commitado em `.env`.

Recomendação:

- configurar no deploy deste backend a variável `GOOGLE_MAPS_KEY` com o mesmo valor já usado no `toca-delivery`;
- opcionalmente preencher também `NEXT_PUBLIC_GOOGLE_MAPS_KEY` apenas se algum frontend deste ecossistema realmente precisar carregar Maps JS direto;
- não copiar segredo para arquivo versionado;
- revisar restrições da chave no Google Cloud:
  - APIs habilitadas
  - quotas
  - restrição por IP/referrer/app
  - billing centralizado

Risco:

- se a chave atual estiver restrita a hostnames do `toca-delivery`, o backend Django não conseguirá usar as APIs server-side;
- nesse caso o correto é ajustar restrições no Google Cloud ou emitir uma chave server-side separada para este backend.

## 8. Escopo de integração futura com `toca-delivery`

### 8.1 Visão maior

O `server2` atende venda, checkout, automação e atendimento. O `toca-delivery` é candidato natural a atuar como motor logístico externo.

Arquitetura sugerida:

- `server2` continua dono do pedido, catálogo, cliente, pagamento e experiência conversacional;
- `toca-delivery` vira orquestrador de despacho/entrega;
- integração por eventos ou API síncrona controlada.

### 8.2 Fronteira de responsabilidade

`server2` deve continuar responsável por:

- criação do pedido;
- cálculo comercial final;
- aceitação do endereço no checkout;
- comunicação com cliente;
- status comercial do pedido.

`toca-delivery` deve ser responsável por:

- alocação de entregador;
- rastreio operacional;
- rota operacional ativa;
- ETA operacional;
- eventos de coleta/em rota/entregue.

### 8.3 Modelo de integração recomendado

Criar uma camada `DeliveryProvider` no domínio de lojas:

- `InternalDeliveryProvider`
- `TocaDeliveryProvider`

Operações mínimas:

- `quote_delivery(order_context)`
- `create_delivery(order_context)`
- `cancel_delivery(external_delivery_id)`
- `refresh_delivery_status(external_delivery_id)`
- `webhook_update(payload)`

Payload mínimo de integração:

- `order_id`
- `store_id`
- `pickup`
- `dropoff`
- `customer`
- `items_summary`
- `declared_value`
- `delivery_notes`
- `contact_phone`

### 8.4 Ordem correta de execução

A sequência arquitetural certa é:

1. desacoplar HERE e estabilizar geocamada;
2. consolidar contrato canônico de endereço/rota;
3. introduzir `DeliveryProvider`;
4. integrar `toca-delivery`.

Se o time inverter isso, vai integrar um sistema terceiro em cima de um contrato geográfico ainda instável.

## 9. Pontos críticos e riscos

### 9.1 Riscos técnicos

- quebra de mocks e testes que referenciam `HereMapsService`;
- quebra de parsing de endereço no WhatsApp;
- diferença de precisão entre HERE e Google em Palmas;
- diferença de custo e quota por endpoint;
- isoline sem substituto direto;
- billing não preparado para volume de autosuggest.

### 9.2 Riscos de produto/operação

- taxa de entrega mudar silenciosamente;
- cliente visualizar mapa correto, mas backend calcular fee divergente;
- rejeição de endereço válido por excesso de validação;
- integração logística futura herdar inconsistência de endereço.

### 9.3 Riscos de segurança/governança

- vazamento de chave no repositório;
- uso de chave frontend em backend sem restrição adequada;
- billing compartilhado sem observabilidade por serviço.

## 10. Métricas de sucesso

KPIs técnicos:

- taxa de erro de geocode;
- taxa de erro de reverse geocode;
- tempo médio de resposta por endpoint de mapa;
- percentual de fallback haversine;
- divergência entre distância calculada e rota exibida;
- percentual de pedidos com endereço corrigido manualmente.

KPIs de negócio:

- redução de entregas com endereço incorreto;
- redução de pedidos recusados por geocodificação errada;
- redução de tickets humanos ligados a localização;
- aumento da conversão no checkout de delivery;
- aumento da precisão do ETA percebido.

## 11. Plano de testes

### 11.1 Testes unitários

Cobrir:

- normalização de geocode Google -> contrato canônico;
- normalização de reverse geocode Google -> contrato canônico;
- directions Google -> `distance_km`, `duration_minutes`, `polyline`;
- fallback haversine quando a API falhar;
- compatibilidade de `delivery_address` no WhatsApp.

### 11.2 Testes de integração

Cobrir endpoints:

- `/api/v1/stores/maps/geocode/`
- `/api/v1/stores/maps/reverse-geocode/`
- `/api/v1/stores/maps/autosuggest/`
- `/api/v1/stores/{slug}/route/`
- `/api/v1/stores/{slug}/maps/validate-delivery/`
- cálculo de taxa no checkout

### 11.3 Testes de regressão de negócio

Cenários mínimos:

- endereço textual completo em Palmas;
- CEP sem número;
- localização compartilhada via lat/lng;
- bairro com taxa fixa;
- endereço fora da área;
- pedido via WhatsApp com geocode;
- reverse geocode a partir de GPS no WhatsApp.

## 12. Backlog técnico recomendado

### Sprint 1. Fundação

- criar `geo_service` canônico;
- adicionar `GOOGLE_MAPS_KEY` em settings;
- implementar provider Google;
- manter compatibilidade temporária com imports antigos.

### Sprint 2. Migração de consumidores

- trocar `maps_views` para `geo_service`;
- trocar checkout/storefront para `geo_service`;
- trocar handlers e order service do WhatsApp;
- atualizar testes e mocks.

### Sprint 3. Endurecimento operacional

- feature flag por provider;
- métricas e logs por endpoint/provider;
- auditoria de custos e quota;
- remoção do legado HERE.

### Sprint 4. Pronto para logística externa

- introduzir `DeliveryProvider`;
- modelar `external_delivery_id`, `delivery_provider`, `delivery_status_external`;
- desenhar webhooks/retentativas;
- integrar `toca-delivery`.

## 13. Decisões recomendadas

Decisões que eu recomendo tomar agora:

1. Google passa a ser o provider geoespacial primário.
2. O backend continua sendo dono da polyline e da distância operacional exposta ao frontend.
3. O contrato interno passa a ser canônico e independente de provider.
4. Isoline deixa de ser premissa da arquitetura principal.
5. Integração com `toca-delivery` entra somente depois da estabilização da geocamada.

## 14. Próximo passo recomendado

Próxima execução de maior valor:

- implementar a abstração `geo_service`;
- adicionar `GOOGLE_MAPS_KEY` em `config/settings/base.py`;
- portar geocode, reverse geocode, route e autosuggest para Google;
- manter o payload externo compatível;
- ajustar testes que hoje referenciam `HereMapsService`.

Isso entrega valor técnico imediato, reduz risco de endereço errado e prepara a base para a integração logística posterior.
