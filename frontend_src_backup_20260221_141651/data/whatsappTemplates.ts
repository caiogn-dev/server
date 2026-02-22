export interface WhatsAppTemplate {
  id: string;
  name: string;
  description: string;
  category: 'transactional' | 'marketing' | 'support';
  content: string;
  variables: string[];
}

export const whatsappTemplates: WhatsAppTemplate[] = [
  {
    id: 'welcome',
    name: 'Boas-vindas',
    description: 'Mensagem de boas-vindas para novos clientes',
    category: 'transactional',
    content: `Olá {{nome}}! 👋\n\nSeja bem-vindo(a) à *Pastita - Massas Artesanais*!\n\n🍝 Aqui você encontra as melhores massas frescas feitas com carinho.\n\n📍 Palmas/TO | ⏰ Ter-Dom 11h-21h\n\nAcesse: https://pastita.com.br`,
    variables: ['nome']
  },
  {
    id: 'order_confirmed',
    name: 'Confirmação de Pedido',
    description: 'Confirmação recebimento do pedido',
    category: 'transactional',
    content: `✅ *Pedido Confirmado!*\n\nOlá {{nome}}, recebemos seu pedido #{{pedido}}.\n\n💰 *Total:* R$ {{valor}}\n⏱️ *Tempo:* {{tempo}} min\n\nVamos preparar com carinho! 🍝`,
    variables: ['nome', 'pedido', 'valor', 'tempo']
  },
  {
    id: 'order_preparing',
    name: 'Pedido em Preparação',
    description: 'Avisa cliente que pedido está sendo preparado',
    category: 'transactional',
    content: `👨‍🍳 *Seu pedido está sendo preparado!*\n\nOlá {{nome}},\n\nPedido #{{pedido}} em preparação.\n⏱️ Falta aproximadamente {{tempo}} minutos!`,
    variables: ['nome', 'pedido', 'tempo']
  },
  {
    id: 'order_delivery',
    name: 'Saiu para Entrega',
    description: 'Notifica que pedido saiu para entrega',
    category: 'transactional',
    content: `🛵 *Seu pedido saiu para entrega!*\n\nOlá {{nome}},\n\nPedido #{{pedido}} a caminho!\n📍 {{endereco}}\n⏱️ Chega em {{tempo}} min`,
    variables: ['nome', 'pedido', 'endereco', 'tempo']
  },
  {
    id: 'order_delivered',
    name: 'Pedido Entregue',
    description: 'Confirma entrega e solicita avaliação',
    category: 'transactional',
    content: `✨ *Pedido Entregue!*\n\nOlá {{nome}},\n\nSeu pedido #{{pedido}} foi entregue! 🎉\n\nEsperamos que aproveite!\nAvalie: {{link}}`,
    variables: ['nome', 'pedido', 'link']
  },
  {
    id: 'coupon',
    name: 'Cupom de Desconto',
    description: 'Envia cupom de desconto promocional',
    category: 'marketing',
    content: `🎁 *Cupom especial para você!*\n\nOlá {{nome}},\n\n🏷️ *{{cupom}}*\n💰 *{{desconto}}% OFF*\n⏰ Válido até: {{data}}\n\n👉 {{link}}`,
    variables: ['nome', 'cupom', 'desconto', 'data', 'link']
  },
  {
    id: 'reengagement',
    name: 'Reengajamento',
    description: 'Traz cliente de volta com oferta especial',
    category: 'marketing',
    content: `👋 *Sentimos sua falta, {{nome}}!*\n\nPreparamos algo especial:\n🏷️ *{{cupom}}* - *{{desconto}}% OFF*\n\nVálido por 3 dias!\n👉 {{link}}`,
    variables: ['nome', 'cupom', 'desconto', 'link']
  },
  {
    id: 'birthday',
    name: 'Aniversário',
    description: 'Parabeniza cliente com desconto especial',
    category: 'marketing',
    content: `🎂 *Feliz Aniversário, {{nome}}!*\n\n🎁 *PARABENS{{idade}}*\n*{{desconto}}% OFF* válido hoje!\n\nComemore com nossas massas 🍝\n{{link}}`,
    variables: ['nome', 'idade', 'desconto', 'link']
  },
  {
    id: 'abandoned_cart',
    name: 'Abandono de Carrinho',
    description: 'Recupera vendas de carrinhos abandonados',
    category: 'marketing',
    content: `🛒 *Esqueceu algo, {{nome}}?*\n\nItens reservados por 30 min!\n\nUse *{{cupom}}* para *{{desconto}}% OFF*\n👉 {{link}}`,
    variables: ['nome', 'cupom', 'desconto', 'link']
  }
];

export const getTemplateById = (id: string) => whatsappTemplates.find(t => t.id === id);
export const getTemplatesByCategory = (category: WhatsAppTemplate['category']) => 
  whatsappTemplates.filter(t => t.category === category);
