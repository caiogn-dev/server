---
title: Design - Population Scripts for 3 Stores (Cê Saladas, Pastita, Kero Kero)
date: 2026-05-29
status: draft
---

# Consolidação e Otimização: Scripts de População das 3 Lojas

## 1. Objetivo

Consolidar e melhorar 3 scripts de população fragmentados (`populate_ce_saladas_menu.py`, `populate_pastita_menu.py`, `populate_kero_kero_menu.py`) em um **master script unificado** que:

- Popula dados completos das 3 lojas (Store, categorias, produtos)
- Integra WhatsApp Business Account (apenas Cê Saladas)
- Otimiza todas as imagens para WebP antes de salvar
- Aplica dados reais (coordenadas, horário, taxas de entrega, etc)
- Fornece logs estruturados por fase/tabela

---

## 2. Dados Compartilhados (todas as 3 lojas)

### Localização
```python
SHARED_LOCATION = {
    "latitude": Decimal("-10.1852683"),
    "longitude": Decimal("-48.3036368"),
    "address": "Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins",
    "city": "Palmas",
    "state": "TO",
    "zip_code": "72000-000",
    "country": "BR",
}
```

### Horário de Funcionamento
```python
SHARED_OPERATING_HOURS = {
    "monday": {"open": "08:00", "close": "17:00"},
    "tuesday": {"open": "08:00", "close": "17:00"},
    "wednesday": {"open": "08:00", "close": "17:00"},
    "thursday": {"open": "08:00", "close": "17:00"},
    "friday": {"open": "08:00", "close": "17:00"},
    "saturday": {"open": "08:00", "close": "17:00"},
    "sunday": {"open": "00:00", "close": "00:00"},  # Fechado
}
```

### Configurações de Negócio
| Campo | Valor |
|-------|-------|
| `currency` | BRL |
| `timezone` | America/Sao_Paulo |
| `tax_rate` | 0.00 |
| `delivery_enabled` | True |
| `pickup_enabled` | True |

---

## 3. Dados Específicos por Loja

### 3.1 Cê Saladas

**Store Fields:**
| Campo | Valor |
|-------|-------|
| `name` | Cê Saladas |
| `slug` | ce-saladas |
| `store_type` | FOOD |
| `status` | ACTIVE |
| `email` | (sem email) |
| `phone` | 63991386719 |
| `whatsapp_number` | 63991386719 |
| `primary_color` | #2E7D32 (extrair da logo depois) |
| `secondary_color` | #F9A825 |
| `min_order_value` | 0.00 |
| `default_delivery_fee` | 8.00 |
| `free_delivery_threshold` | 100.00 |

**WhatsApp Business Account (NEW):**
```python
{
    "name": "Cê Saladas Official",
    "phone_number_id": "941408229062882",
    "waba_id": "1537842617304215",
    "phone_number": "63991386719",
    "display_phone_number": "+55 63 9 9138-6719",
    "status": "ACTIVE",
    "auto_response_enabled": True,
    "human_handoff_enabled": True,
    # access_token: será adicionado depois (ENV var)
}
```

**Produtos:**
- 7 saladas com nomes específicos
- Todas com imagens em `/home/graco/ftp-data/cardapio-cesaladas/ce-saladas/`
- Imagens otimizadas para WebP (redimensionadas, comprimidas)

Nomes:
1. Tilápia Suprema
2. Especial Filé de Frango
3. Basic Lombo
4. Salmão Sublime
5. Almôndega Premium
6. Queridinha
7. Magnifico Camarão

---

### 3.2 Pastita

**Store Fields:**
| Campo | Valor |
|-------|-------|
| `name` | Pastita |
| `slug` | pastita |
| `store_type` | FOOD |
| `status` | ACTIVE |
| `email` | pastita.oficial@gmail.com |
| `phone` | 63991172166 |
| `whatsapp_number` | 63991172166 |
| `primary_color` | (extrair da logo depois) |
| `secondary_color` | (extrair da logo depois) |
| `min_order_value` | 0.00 |
| `default_delivery_fee` | 10.00 |
| `free_delivery_threshold` | 100.00 |

**Produtos:**
- Menu consolidado de `/scripts/populate_pastita_menu.py` (rondelli, molhos, etc)
- Imagens em `/home/graco/ftp-data/cardapio-cesaladas/pastita/`
- Otimizadas para WebP

---

### 3.3 Kero Kero

**Store Fields:**
| Campo | Valor |
|-------|-------|
| `name` | Kero Kero |
| `slug` | kero-kero |
| `store_type` | FOOD |
| `status` | ACTIVE |
| `email` | (sem email) |
| `phone` | 63992332803 |
| `whatsapp_number` | 63992332803 |
| `primary_color` | (extrair da logo depois) |
| `secondary_color` | (extrair da logo depois) |
| `min_order_value` | 0.00 |
| `default_delivery_fee` | 7.00 |
| `free_delivery_threshold` | 80.00 |

**Produtos:**
- 11 produtos em 8 categorias (já definidos no script original)
- Imagens em `/home/graco/ftp-data/kerokero/generated/`
- Otimizadas para WebP

---

## 4. Arquitetura da Solução

### 4.1 Master Script: `scripts/populate_all_stores.py`

Orquestra a execução faseada:

```bash
# Executar todas as 3 lojas
python manage.py populate_all_stores --all

# Ou individuais
python manage.py populate_all_stores --store=ce-saladas --optimize-images
python manage.py populate_all_stores --store=pastita --optimize-images
python manage.py populate_all_stores --store=kero-kero --optimize-images
```

**Fases de Execução (sequencial):**

1. **Fase 1: Stores**
   - Cria/atualiza 3 lojas com dados + localização

2. **Fase 2: WhatsApp Account** (apenas Cê Saladas)
   - Cria WhatsAppAccount
   - Liga com Store via FK `whatsapp_account`

3. **Fase 3: StoreCategory**
   - Popula categorias de cada loja
   - Imagens otimizadas

4. **Fase 4: StoreProductType**
   - Tipos de produtos (rondelli, molho, etc)

5. **Fase 5: StoreProduct**
   - Popula produtos
   - **Otimiza imagens** (redimensiona, converte WebP, comprime)

6. **Fase 6: StoreDeliveryZone**
   - Popula zonas de entrega com tabela de preços por km

### 4.2 Classe ImageOptimizer

Aplica otimizações antes de salvar imagens:

```python
class ImageOptimizer:
    def optimize(self, image_path, max_width=600, max_height=600):
        """
        Redimensiona mantendo aspect ratio (max 600x600px)
        Converte para WebP
        Retorna novo caminho ou URL S3
        """
        pass
```

**Aplicado em:**
- Category images
- Product main images
- Product gallery images
- Store logos/banners

### 4.3 Melhorias nos Scripts Existentes

**populate_ce_saladas_menu.py:**
- ✅ Já existe (restaurado do Git)
- ➕ Adicionar WhatsAppAccount creation
- ➕ Integrar ImageOptimizer
- ➕ Adicionar dados reais (coords, horário, delivery fees)

**populate_kero_kero_menu.py:**
- ✅ Já existe (restaurado do Git)
- ➕ Integrar ImageOptimizer
- ➕ Adicionar dados reais

**populate_pastita_menu.py:**
- Consolidar 3 scripts (`/scripts/`, `/scripts/populate_pastita_menu_complete.py`, management command)
- ➕ Unificar estrutura com as outras 2
- ➕ Integrar ImageOptimizer

---

## 5. Delivery Zones (Tabela de Preços por KM)

**Tabela Única para as 3 lojas:**

| Distância | Taxa |
|-----------|------|
| 0 - 2 km | R$ 7,00 |
| 2,1 - 3 km | R$ 8,00 |
| 3,1 - 5 km | R$ 9,00 |
| 5,1 - 6 km | R$ 10,00 |
| 6,1 - 6,9 km | R$ 11,00 |
| 7 - 7,9 km | R$ 12,00 |
| 8 km | R$ 13,00 |
| 9 km | R$ 14,00 |
| 10 km | R$ 15,00 |
| 11 km | R$ 16,00 |
| 12 km | R$ 18,00 |
| 13 km | R$ 20,00 |
| 14 km | R$ 22,00 |
| 15 km | R$ 24,00 |
| 16 km | R$ 26,00 |
| 17 km | R$ 28,00 |

**Estrutura de dados para StoreDeliveryZone:**

```python
DELIVERY_ZONES = [
    {
        "name": "0-2km",
        "zone_type": "distance_band",
        "distance_band": "0-2",
        "min_km": 0,
        "max_km": 2,
        "delivery_fee": Decimal("7.00"),
        "sort_order": 1,
    },
    {
        "name": "2.1-3km",
        "zone_type": "distance_band",
        "distance_band": "2.1-3",
        "min_km": Decimal("2.1"),
        "max_km": 3,
        "delivery_fee": Decimal("8.00"),
        "sort_order": 2,
    },
    # ... resto das zonas (16 no total)
]
```

Aplicado a **todas as 3 lojas** (mesmo conjunto de zonas).

---

## 6. Fluxo de Dados

```
Master Script (populate_all_stores.py)
    │
    ├─→ populate_ce_saladas_menu.py
    │   ├─ Create Store
    │   ├─ Create WhatsAppAccount
    │   ├─ Create Categories (+ image optimization)
    │   ├─ Create Products (7 salads, + image optimization)
    │   └─ Create DeliveryZones (16 zonas)
    │
    ├─→ populate_pastita_menu.py
    │   ├─ Create Store
    │   ├─ Create Categories
    │   ├─ Create Products (+ image optimization)
    │   └─ Create DeliveryZones (16 zonas)
    │
    └─→ populate_kero_kero_menu.py
        ├─ Create Store
        ├─ Create Categories (8)
        ├─ Create Products (11, + image optimization)
        └─ Create DeliveryZones (16 zonas)
```

---

## 7. Logging e Progresso

Saída estruturada por fase:

```
✅ FASE 1: Stores
   ├─ Cê Saladas (created) - WABA 1537842617304215
   ├─ Pastita (created)
   └─ Kero Kero (created)

✅ FASE 2: WhatsApp Accounts
   └─ Cê Saladas WhatsAppAccount ACTIVE

✅ FASE 3: Categories
   ├─ Cê Saladas: 1 categoria (Saladas Especiais)
   ├─ Pastita: 3 categorias (Rondelli, Molhos, Promoções)
   └─ Kero Kero: 8 categorias

✅ FASE 4: Product Types
   ├─ Rondelli, Molho, etc.

✅ FASE 5: Products + Image Optimization
   ├─ Cê Saladas: 7 salads (images optimized to WebP)
   ├─ Pastita: N produtos (images optimized to WebP)
   └─ Kero Kero: 11 produtos (images optimized to WebP)

✅ FASE 6: Delivery Zones
   ├─ Cê Saladas: 16 delivery zones (0-17 km)
   ├─ Pastita: 16 delivery zones (0-17 km)
   └─ Kero Kero: 16 delivery zones (0-17 km)
   
📊 Summary:
   - Stores: 3 created
   - WhatsApp Accounts: 1 created (Cê Saladas)
   - Categories: 12 created
   - Products: 29 created
   - Delivery Zones: 48 created (16 por loja)
   - Images optimized: 42 files → WebP
```

---

## 8. Dados de Entrada (Fontes)

| Loja | Fonte | Formato |
|------|-------|---------|
| Cê Saladas | `/home/graco/ftp-data/cardapio-cesaladas/ce-saladas/` | Arquivos de imagem |
| Pastita | `/home/graco/ftp-data/cardapio-cesaladas/pastita/` | Arquivos de imagem |
| Kero Kero | `/home/graco/ftp-data/kerokero/generated/` | Arquivos de imagem |

Produtos (dados hardcoded nos scripts, já definidos)

---

## 9. Validação e Tratamento de Erros

- ✅ Valida existência de imagens (se não existir, usa URL placeholder)
- ✅ Trata erros de otimização (fallback para imagem original)
- ✅ Transaction atomic por loja (rollback se falhar)
- ✅ Log de warnings para imagens não encontradas
- ✅ Opção `--force` para sobrescrever dados existentes

---

## 10. Próximas Etapas (Faseadas)

1. **Sprint 1:** ImageOptimizer class + master script scaffold
2. **Sprint 2:** Integrar Cê Saladas (+ WhatsAppAccount)
3. **Sprint 3:** Integrar Pastita (consolidar 3 scripts)
4. **Sprint 4:** Integrar Kero Kero
5. **Sprint 5:** Testes + delivery zones (se necessário)

---

## 11. Dependências

- Pillow (image optimization)
- Django ORM
- Existing: `populate_ce_saladas_menu.py`, `populate_kero_kero_menu.py`

---

## Checklist de Validação

- [ ] Master script funciona com `--all`
- [ ] WhatsAppAccount criada corretamente para Cê Saladas
- [ ] Todas as imagens otimizadas para WebP
- [ ] Logs estruturados por fase
- [ ] 3 lojas com dados reais
- [ ] Delivery settings corretos
- [ ] Transaction rollback se falhar
- [ ] Testes com dados de desenvolvimento
