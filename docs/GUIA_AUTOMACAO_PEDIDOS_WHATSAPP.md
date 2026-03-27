# 📱 Guia: Automação de Mensagens de Status de Pedidos via WhatsApp

## ✅ O que já está implementado

Seu sistema **envia automaticamente** mensagens WhatsApp quando o pedido muda de status:

```
Status               | Emoji | Mensagem Padrão
--------------------|-------|----------------------------------
CONFIRMED            | ✅    | "Pedido Confirmado!"
PAID                 | 💰    | "Pagamento Confirmado!"
PREPARING            | 👨‍🍳   | "Pedido em Preparo!"
READY                | 📦    | "Pedido Pronto!"
SHIPPED              | 🚚    | "Pedido Enviado!"
DELIVERED            | 📦    | "Pedido Entregue!"
CANCELLED            | ❌    | "Pedido Cancelado"
```

---

## 🔧 Como funciona

### 1️⃣ **Fluxo Automático**

Quando você atualiza um pedido para um novo status:

```python
# No seu backend/admin:
order.update_status(new_status='confirmed', notify=True)
```

**Automaticamente:**
1. ✅ Status é atualizado
2. 📱 Mensagem WhatsApp é enviada instantaneamente
3. 📧 Email é enviado (se configurado)
4. 🔔 Webhook é disparado

### 2️⃣ **Onde as mensagens são enviadas**

A mensagem é enviada para:
- **Número do cliente**: Armazenado em `order.customer_phone`
- **Via conta WhatsApp**: Vinculada ao seu `Store` (ce-saladas)
- **Qualidade**: Usando Queue (Celery) + Retry automático se falhar

### 3️⃣ **Templates de mensagens**

Os templates padrão usam o formato:

```
Mensagem base: "✅ *Pedido Confirmado!*\n\nOlá {customer_name}!\n\nSeu pedido #{order_number} foi confirmado!"
```

**Variáveis disponíveis:**
- `{customer_name}` - Nome do cliente
- `{order_number}` - Número do pedido (ex: CE-2603146308)

---

## 🎯 Exemplo de Uso

### Cenário: Cliente comprou, agora é preparo

```bash
# Request HTTP para atualizar status
POST /api/v1/stores/orders/{order_id}/update_status/
{
    "status": "preparing",
    "notify": true
}
```

**Resultado automático:**
```
👨‍🍳 *Pedido em Preparo!*

Olá João Silva!

Seu pedido #CE-2603146308 está sendo preparado!
```
Enviado em < 2 segundos para: +55 11 98765-4321 ✅

---

## 📋 Checklist: Garantir que funcione

- [ ] ✅ Conta WhatsApp configurada e ativa no seu sistema
- [ ] ✅ `order.customer_phone` preenchido no momento da compra
- [ ] ✅ `order.customer_name` preenchido
- [ ] ✅ Celery rodando (worker processando tasks em background)
- [ ] ✅ Números de telefone em formato internacional (+55...)

### ⚠️ Se não for enviar:

**Debug: Checar logs**
```bash
# No seu servidor:
docker logs pastita_celery | grep "notify_order_status_change"
docker logs pastita_web | grep "status_whatsapp_notification"
```

**Problemas comuns:**
1. ❌ Celery não está rodando → fila de mensagens não processa
2. ❌ Conta WhatsApp desativada → sem credenciais
3. ❌ Telefone inválido/incompleto → erro de envio
4. ❌ Número não tem WhatsApp Business → rejeita

---

## 🎨 Customização: Mudar mensagens

### Opção 1: Backend apenas (Código Python)

Edite em `apps/stores/models/order.py`, linha ~235:

```python
status_message_map = {
    self.OrderStatus.CONFIRMED: "Sua mensagem customizada aqui #{order_number}",
    # ... outros status
}
```

✅ Após edit: Faz commit → Push → Docker restart

### Opção 2: Admin Panel (Recomendado)

Se implementarmos AutoMessage templates em admin django:

```bash
GET /admin/automation/automessage/
# Cria/edita templates por event_type
```

---

## 📊 Monitorar envios

### Ver histórico de mensagens enviadas

```bash
# Query de exemplo
curl -X GET "https://backend.pastita.com.br/api/v1/whatsapp/messages/?order_id=XXX" \
  -H "Authorization: Bearer TOKEN"
```

**Campos importante na response:**
- `status`: "delivered" ✅ | "failed" ❌ | "pending" ⏳
- `created_at`: Hora do envio
- `error_message`: Se falhou, por quê

---

## 🚀 Próximos Passos

1. **Testar**: Atualize um pedido para "preparing" e verifique se mensagem chega
2. **Customizar**: Se quiser mudar os textos, edite os templates
3. **Monitorar**: Acompanhe logs de Celery/Django para troubleshoot

---

## 📞 Fluxo Completo de Exemplo

```
1. Cliente compra online
   order.status = 'pending_payment'
   
2. Pagamento confirmado
   order.update_status('confirmed', notify=True)
   ✅ WhatsApp enviado: "Pedido Confirmado!"
   
3. Você começa a preparar
   order.update_status('preparing', notify=True)
   👨‍🍳 WhatsApp enviado: "Pedido em Preparo!"
   
4. Pronto para entrega
   order.update_status('ready', notify=True)
   📦 WhatsApp enviado: "Pedido Pronto!"
   
5. Entregador pega
   order.update_status('shipped', notify=True)
   🚚 WhatsApp enviado: "Pedido Enviado!"
   
6. Entregue ao cliente
   order.update_status('delivered', notify=True)
   📦 WhatsApp enviado: "Pedido Entregue!"
   ⭐ Email + Solicitação de feedback automática
```

---

## ✨ Dicas Extras

- **Sem timeout de entrega**: Sistema tenta reenviar até 3x se falhar
- **Control+Bypass**: Se mandar `notify=false`, pula automação
- **Segurança**: Cada mensagem fica salva no histórico + auditável
- **iOS/Android**: Customers veem notificação normalmente (push WhatsApp)

---

**Status**: ✅ Totalmente funcional e pronto para usar!

Quer testar? Mude um pedido de status e aguarde a mensagem chegar! 📱
