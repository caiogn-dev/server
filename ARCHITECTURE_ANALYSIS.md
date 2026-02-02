# Análise Arquitetural - Pastita Platform

## 📊 Visão Macro

**Total de Apps:** 12  
**Total de Modelos:** 30+  
**Total de Relacionamentos:** 212+  
**Total de Serviços:** 20+  

---

## 🚨 PROBLEMAS CRÍTICOS IDENTIFICADOS

### 1. **DUPLICAÇÃO DE DADOS - Store vs CompanyProfile**

**Severidade:** 🔴 CRÍTICA

**Problema:**
- `Store` já contém: nome, descrição, telefone, email, endereço, horário de funcionamento
- `CompanyProfile` duplica: company_name, description, business_hours
- O usuário precisa preencher os mesmos dados 2 vezes

**Impacto:**
- Inconsistência de dados
- Experiência ruim no dashboard
- Manutenção complexa

**Solução Proposta:**
```python
# Opção 1: CompanyProfile herda/extende Store
class CompanyProfile(models.Model):
    store = models.OneToOneField(Store, on_delete=models.CASCADE)
    # Apenas campos específicos de automação
    auto_reply_enabled = models.BooleanField(default=True)
    welcome_message_enabled = models.BooleanField(default=True)
    # ... (sem duplicação de dados básicos)

# Opção 2: CompanyProfile usa Store como fonte de verdade
@property
def company_name(self):
    return self.store.name

@property
def phone_number(self):
    return self.store.whatsapp_number
```

---

### 2. **FRAGMENTAÇÃO DE SERVIÇOS DE MENSAGEM**

**Severidade:** 🔴 CRÍTICA

**Problema:**
- `apps.whatsapp.services.message_service` - envio básico
- `apps.automation.services.automation_service` - mensagens automáticas
- `apps.campaigns.services.campaign_service` - campanhas em massa
- `apps.instagram.services.message_service` - Instagram
- Cada um com sua própria lógica de envio

**Impacto:**
- Código duplicado
- Inconsistência no tratamento de erros
- Dificuldade de manutenção

**Solução Proposta:**
```
apps/
  messaging/           # NOVO APP UNIFICADO
    services/
      message_dispatcher.py   # Roteia para canal correto
      message_queue.py        # Fila unificada
      message_templates.py    # Templates cross-platform
    channels/
      whatsapp.py            # Adapter WhatsApp
      instagram.py           # Adapter Instagram
      sms.py                 # Adapter SMS (futuro)
```

---

### 3. **ACOPLAMENTO ENTRE STORES E WHATSAPP**

**Severidade:** 🟡 ALTA

**Problema:**
- Store tem `whatsapp_number` (CharField) mas não ForeignKey para WhatsAppAccount
- Não há relação direta entre Store e WhatsAppAccount
- Dificulta integração automation <-> store

**Impacto:**
- Busca por phone_number é frágil
- Não garante que a conta existe
- Dificulta validações

**Solução Proposta:**
```python
class Store(models.Model):
    # ... campos existentes ...
    whatsapp_account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stores'
    )
    # whatsapp_number pode ser @property
    @property
    def whatsapp_number(self):
        return self.whatsapp_account.phone_number if self.whatsapp_account else None
```

---

### 4. **COMPANYPROFILE SEM RELAÇÃO COM STORE**

**Severidade:** 🔴 CRÍTICA

**Problema:**
- CompanyProfile está ligado a WhatsAppAccount
- Mas não tem relação direta com Store
- Automation não sabe qual loja está atendendo

**Impacto:**
- Não consegue acessar produtos, preços, pedidos
- Mensagens automáticas não têm contexto da loja
- Carrinho abandonado não funciona corretamente

**Solução Proposta:**
```python
class CompanyProfile(models.Model):
    # ... campos existentes ...
    store = models.OneToOneField(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='automation_profile',
        null=True, blank=True  # temporário para migração
    )
    
    @property
    def company_name(self):
        return self.store.name if self.store else self._company_name
```

---

### 5. **WEBHOOKS ESPALHADOS E INCONSISTENTES**

**Severidade:** 🟡 ALTA

**Problema:**
- `apps.whatsapp.webhooks` - WhatsApp
- `apps.stores.webhooks_urls` - Pagamentos
- `apps.automation.webhooks` - Automation
- Cada um com estrutura diferente

**Impacto:**
- Dificuldade de manutenção
- Inconsistência de segurança
- Código duplicado de validação

**Solução Proposta:**
```
apps/
  webhooks/            # NOVO APP CENTRALIZADO
    models.py          # WebhookEndpoint, WebhookLog
    services/
      dispatcher.py    # Roteia para handlers
      validator.py     # Validação de assinaturas
    handlers/
      whatsapp.py
      mercadopago.py
      automation.py
```

---

### 6. **PERMISSÕES E AUTENTICAÇÃO INCONSISTENTES**

**Severidade:** 🟡 ALTA

**Problema:**
- Algumas views usam `IsAuthenticated`
- Outras têm permissões customizadas
- Não há padrão de permissão por store

**Impacto:**
- Risco de segurança
- Usuário acessa dados de outras lojas
- Dificuldade de auditoria

**Solução Proposta:**
```python
# Permissão padrão para todas as views de store
class IsStoreOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'store'):
            return obj.store.owner == request.user
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        return False

# Mixin para views
class StorePermissionMixin:
    permission_classes = [IsAuthenticated, IsStoreOwner]
```

---

### 7. **SERIALIZERS DUPLICADOS E INCONSISTENTES**

**Severidade:** 🟡 MÉDIA

**Problema:**
- `CreateCompanyProfileSerializer` - criação
- `UpdateCompanyProfileSerializer` - atualização
- `CompanyProfileSerializer` - leitura
- Lógica repetida em todos

**Impacto:**
- Manutenção triplicada
- Inconsistência de campos
- Bugs de sincronização

**Solução Proposta:**
```python
class CompanyProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyProfile
        fields = [...]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        # Lógica de criação
        pass
    
    def update(self, instance, validated_data):
        # Lógica de atualização
        pass
```

---

## 🏗️ ARQUITETURA PROPOSTA

### Estrutura Unificada

```
apps/
  core/                    # Base models, utils, exceptions
  
  identity/                # Usuários, permissões, autenticação
    models/
      user.py
      permissions.py
  
  commerce/                # Store, produtos, pedidos, pagamentos
    models/
      store.py             # Store unificado
      product.py
      order.py
      payment.py
    services/
      checkout.py
      payment_gateway.py
  
  messaging/               # WhatsApp, Instagram, SMS unificado
    models/
      channel.py           # WhatsApp, Instagram, etc
      message.py
      template.py
    services/
      dispatcher.py        # Roteia para canal correto
      queue.py             # Fila unificada
  
  automation/              # Regras, triggers, workflows
    models/
      workflow.py          # Regras de automação
      trigger.py           # Gatilhos (eventos)
      action.py            # Ações (enviar msg, etc)
    services/
      engine.py            # Motor de automação
  
  webhooks/                # Webhooks centralizados
    models/
      endpoint.py
      log.py
    handlers/
      whatsapp.py
      mercadopago.py
```

---

## 📋 PRIORIDADES DE REFATORAÇÃO

### Fase 1: Fundação (CRÍTICO)
1. ✅ Corrigir PUT endpoint de AutoMessage
2. 🔄 Criar relação Store <-> WhatsAppAccount
3. 🔄 Criar relação CompanyProfile <-> Store
4. 🔄 Remover duplicação Store/CompanyProfile

### Fase 2: Unificação (ALTA)
1. Criar app `messaging` unificado
2. Migrar serviços de mensagem
3. Unificar webhooks
4. Padronizar permissões

### Fase 3: Otimização (MÉDIA)
1. Consolidar serializers
2. Criar testes de integração
3. Documentar APIs
4. Monitoramento

---

## 🔧 IMPLEMENTAÇÃO IMEDIATA

### 1. Adicionar Store em CompanyProfile

```python
# migration
class Migration(migrations.Migration):
    dependencies = [...]
    
    operations = [
        migrations.AddField(
            model_name='companyprofile',
            name='store',
            field=models.OneToOneField(
                to='stores.store',
                on_delete=models.CASCADE,
                null=True, blank=True
            ),
        ),
    ]
```

### 2. Criar Property para Dados da Store

```python
class CompanyProfile(models.Model):
    # ... campos existentes ...
    store = models.OneToOneField(Store, ...)
    
    @property
    def company_name(self):
        return self.store.name if self.store else self._company_name
    
    @property
    def phone_number(self):
        return self.store.whatsapp_number if self.store else None
```

### 3. Atualizar Serviço de Automação

```python
class AutomationService:
    def handle_incoming_message(self, account_id, phone_number, message_text, ...):
        # Buscar CompanyProfile pela Store
        profile = CompanyProfile.objects.filter(
            store__whatsapp_account_id=account_id
        ).first()
        
        if not profile:
            # Fallback para lógica antiga
            profile = self.get_company_profile(account_id)
```

---

## ✅ CHECKLIST DE IMPLEMENTAÇÃO

- [x] Análise arquitetural completa
- [ ] Criar migração Store <-> WhatsAppAccount
- [ ] Criar migração CompanyProfile <-> Store
- [ ] Atualizar CompanyProfile para usar dados da Store
- [ ] Atualizar serializers para pré-preencher dados
- [ ] Testar integração completa
- [ ] Documentar mudanças

---

## 📝 NOTAS

- Manter backward compatibility durante transição
- Criar comandos de migração de dados
- Testar em ambiente de staging antes de produção
- Comunicar mudanças para equipe