import{j as e}from"./vendor-charts-o9Lo7m6Z.js";import{r as d}from"./vendor-react-C2HNIXra.js";import{b1 as v}from"./feature-automation-CLWK1V5x.js";import"./vendor-utils-DaXQUBrP.js";import"./vendor-ui-B9rDAafI.js";import"./vendor-mui-DKuE-Kg_.js";const l=[{id:"welcome",name:"Boas-vindas",description:"Mensagem de boas-vindas para novos clientes",category:"transactional",content:`Olá {{nome}}! 👋

Seja bem-vindo(a) à *Pastita - Massas Artesanais*!

🍝 Aqui você encontra as melhores massas frescas feitas com carinho.

📍 Palmas/TO | ⏰ Ter-Dom 11h-21h

Acesse: https://pastita.com.br`,variables:["nome"]},{id:"order_confirmed",name:"Confirmação de Pedido",description:"Confirmação recebimento do pedido",category:"transactional",content:`✅ *Pedido Confirmado!*

Olá {{nome}}, recebemos seu pedido #{{pedido}}.

💰 *Total:* R$ {{valor}}
⏱️ *Tempo:* {{tempo}} min

Vamos preparar com carinho! 🍝`,variables:["nome","pedido","valor","tempo"]},{id:"order_preparing",name:"Pedido em Preparação",description:"Avisa cliente que pedido está sendo preparado",category:"transactional",content:`👨‍🍳 *Seu pedido está sendo preparado!*

Olá {{nome}},

Pedido #{{pedido}} em preparação.
⏱️ Falta aproximadamente {{tempo}} minutos!`,variables:["nome","pedido","tempo"]},{id:"order_delivery",name:"Saiu para Entrega",description:"Notifica que pedido saiu para entrega",category:"transactional",content:`🛵 *Seu pedido saiu para entrega!*

Olá {{nome}},

Pedido #{{pedido}} a caminho!
📍 {{endereco}}
⏱️ Chega em {{tempo}} min`,variables:["nome","pedido","endereco","tempo"]},{id:"order_delivered",name:"Pedido Entregue",description:"Confirma entrega e solicita avaliação",category:"transactional",content:`✨ *Pedido Entregue!*

Olá {{nome}},

Seu pedido #{{pedido}} foi entregue! 🎉

Esperamos que aproveite!
Avalie: {{link}}`,variables:["nome","pedido","link"]},{id:"coupon",name:"Cupom de Desconto",description:"Envia cupom de desconto promocional",category:"marketing",content:`🎁 *Cupom especial para você!*

Olá {{nome}},

🏷️ *{{cupom}}*
💰 *{{desconto}}% OFF*
⏰ Válido até: {{data}}

👉 {{link}}`,variables:["nome","cupom","desconto","data","link"]},{id:"reengagement",name:"Reengajamento",description:"Traz cliente de volta com oferta especial",category:"marketing",content:`👋 *Sentimos sua falta, {{nome}}!*

Preparamos algo especial:
🏷️ *{{cupom}}* - *{{desconto}}% OFF*

Válido por 3 dias!
👉 {{link}}`,variables:["nome","cupom","desconto","link"]},{id:"birthday",name:"Aniversário",description:"Parabeniza cliente com desconto especial",category:"marketing",content:`🎂 *Feliz Aniversário, {{nome}}!*

🎁 *PARABENS{{idade}}*
*{{desconto}}% OFF* válido hoje!

Comemore com nossas massas 🍝
{{link}}`,variables:["nome","idade","desconto","link"]},{id:"abandoned_cart",name:"Abandono de Carrinho",description:"Recupera vendas de carrinhos abandonados",category:"marketing",content:`🛒 *Esqueceu algo, {{nome}}?*

Itens reservados por 30 min!

Use *{{cupom}}* para *{{desconto}}% OFF*
👉 {{link}}`,variables:["nome","cupom","desconto","link"]}],i=t=>l.filter(n=>n.category===t),T=()=>{const[t,n]=d.useState("all"),[s,g]=d.useState(null),[c,m]=d.useState({}),x=t==="all"?l:i(t),h=a=>{switch(a){case"transactional":return"info";case"marketing":return"purple";case"support":return"success";default:return"gray"}},p=a=>{switch(a){case"transactional":return"Transacional";case"marketing":return"Marketing";case"support":return"Suporte";default:return a}},u=a=>{g(a);const r={};a.variables.forEach(o=>{r[o]=""}),m(r)},b=()=>{if(!s)return"";let a=s.content;return Object.entries(c).forEach(([r,o])=>{a=a.replace(new RegExp(`{{${r}}}`,"g"),o||`{{${r}}}`)}),a};return e.jsxs("div",{className:"p-6 max-w-7xl mx-auto",children:[e.jsxs("div",{className:"mb-8",children:[e.jsx("h1",{className:"text-3xl font-bold text-gray-900 mb-2",children:"Templates WhatsApp"}),e.jsx("p",{className:"text-gray-600",children:"Gerencie templates de mensagens para disparos automatizados"})]}),e.jsxs("div",{className:"grid grid-cols-4 gap-4 mb-8",children:[e.jsxs("div",{className:"bg-white rounded-lg shadow p-4",children:[e.jsx("div",{className:"text-2xl font-bold text-gray-900",children:l.length}),e.jsx("div",{className:"text-sm text-gray-500",children:"Total Templates"})]}),e.jsxs("div",{className:"bg-white rounded-lg shadow p-4",children:[e.jsx("div",{className:"text-2xl font-bold text-blue-600",children:i("transactional").length}),e.jsx("div",{className:"text-sm text-gray-500",children:"Transacionais"})]}),e.jsxs("div",{className:"bg-white rounded-lg shadow p-4",children:[e.jsx("div",{className:"text-2xl font-bold text-purple-600",children:i("marketing").length}),e.jsx("div",{className:"text-sm text-gray-500",children:"Marketing"})]}),e.jsxs("div",{className:"bg-white rounded-lg shadow p-4",children:[e.jsx("div",{className:"text-2xl font-bold text-green-600",children:i("support").length}),e.jsx("div",{className:"text-sm text-gray-500",children:"Suporte"})]})]}),e.jsxs("div",{className:"grid grid-cols-2 gap-8",children:[e.jsxs("div",{children:[e.jsx("div",{className:"flex gap-2 mb-4",children:["all","transactional","marketing","support"].map(a=>e.jsx("button",{onClick:()=>n(a),className:`px-4 py-2 rounded-lg font-medium transition-colors ${t===a?"bg-violet-600 text-white":"bg-gray-100 text-gray-700 hover:bg-gray-200"}`,children:a==="all"?"Todos":p(a)},a))}),e.jsx("div",{className:"space-y-3",children:x.map(a=>e.jsxs("div",{onClick:()=>u(a),className:`p-4 rounded-lg border-2 cursor-pointer transition-all hover:shadow-md ${s?.id===a.id?"border-violet-500 bg-violet-50":"border-gray-200 bg-white"}`,children:[e.jsxs("div",{className:"flex items-start justify-between mb-2",children:[e.jsx("h3",{className:"font-semibold text-gray-900",children:a.name}),e.jsx(v,{variant:h(a.category),children:p(a.category)})]}),e.jsx("p",{className:"text-sm text-gray-600 mb-3",children:a.description}),e.jsx("div",{className:"flex flex-wrap gap-1",children:a.variables.map(r=>e.jsx("span",{className:"text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded",children:`{{${r}}}`},r))})]},a.id))})]}),e.jsx("div",{children:s?e.jsxs("div",{className:"bg-white rounded-lg shadow-lg border border-gray-200 sticky top-6",children:[e.jsxs("div",{className:"p-4 border-b border-gray-200 bg-gray-50 rounded-t-lg",children:[e.jsx("h2",{className:"font-semibold text-gray-900",children:"Preview"}),e.jsx("p",{className:"text-sm text-gray-500",children:s.name})]}),e.jsxs("div",{className:"p-4 border-b border-gray-200",children:[e.jsx("h3",{className:"text-sm font-medium text-gray-700 mb-3",children:"Variáveis"}),e.jsx("div",{className:"space-y-3",children:s.variables.map(a=>e.jsxs("div",{children:[e.jsx("label",{className:"block text-xs text-gray-500 mb-1 capitalize",children:a}),e.jsx("input",{type:"text",value:c[a]||"",onChange:r=>m(o=>({...o,[a]:r.target.value})),className:"w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-violet-500 focus:border-violet-500",placeholder:`Valor para {{${a}}}`})]},a))})]}),e.jsx("div",{className:"p-4 bg-[#e5ddd5] min-h-[300px]",children:e.jsxs("div",{className:"bg-white rounded-lg rounded-tl-none shadow-sm p-3 max-w-[90%] relative",children:[e.jsx("div",{className:"absolute -left-2 top-0 w-0 h-0 border-t-[10px] border-t-transparent border-r-[10px] border-r-white border-b-[10px] border-b-transparent"}),e.jsx("pre",{className:"text-sm text-gray-800 whitespace-pre-wrap font-sans",children:b()}),e.jsx("div",{className:"text-right mt-1",children:e.jsx("span",{className:"text-xs text-gray-400",children:new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})})})]})}),e.jsxs("div",{className:"p-4 border-t border-gray-200 flex gap-3",children:[e.jsx("button",{className:"flex-1 bg-violet-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-violet-700 transition-colors",children:"Usar Template"}),e.jsx("button",{className:"px-4 py-2 border border-gray-300 rounded-lg font-medium text-gray-700 hover:bg-gray-50 transition-colors",children:"Editar"})]})]}):e.jsxs("div",{className:"bg-gray-50 rounded-lg border-2 border-dashed border-gray-300 p-12 text-center",children:[e.jsx("div",{className:"text-4xl mb-4",children:"📱"}),e.jsx("h3",{className:"text-lg font-medium text-gray-900 mb-2",children:"Selecione um template"}),e.jsx("p",{className:"text-gray-500",children:"Clique em um template à esquerda para visualizar"})]})})]})]})};export{T as default};
