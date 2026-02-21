import{j as e}from"./vendor-charts-o9Lo7m6Z.js";import{r as u,u as H,e as q}from"./vendor-react-C2HNIXra.js";import{d as W,an as f,aE as X,R as T,Z as L,$ as G,ac as V,a4 as y,ax as Y,t as Z,ay as J,aF as K,D as U,ah as Q,X as M,z as F,M as D,aw as ee,F as te,p as se}from"./feature-automation-CLWK1V5x.js";import"./index-DQDVHdIA.js";import{g as ae}from"./vendor-utils-DaXQUBrP.js";import"./vendor-ui-B9rDAafI.js";import"./vendor-mui-DKuE-Kg_.js";const re=()=>{const d=u.useRef(null);return{printOrder:u.useCallback((a,l)=>{if(!d.current){const s=document.createElement("iframe");s.style.position="absolute",s.style.top="-9999px",s.style.left="-9999px",s.style.width="80mm",s.style.height="0",document.body.appendChild(s),d.current=s}const n=d.current,p=n.contentDocument||n.contentWindow?.document;if(!p){console.error("Could not access iframe document");return}const j=s=>new Date(s).toLocaleString("pt-BR",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"}),t=s=>`R$ ${(typeof s=="string"?parseFloat(s):s).toFixed(2).replace(".",",")}`,k=()=>{const c=a.endereco_entrega||a.delivery_address;if(!c||typeof c!="object")return"";const o=c,x=[];return(o.rua||o.street)&&x.push(o.rua||o.street),(o.numero||o.number)&&x.push(`nº ${o.numero||o.number}`),(o.complemento||o.complement)&&x.push(o.complemento||o.complement),(o.bairro||o.neighborhood)&&x.push(o.bairro||o.neighborhood),x.join(", ")},z=()=>(a.delivery_method||"delivery")==="pickup"?"🏪 RETIRADA":"🛵 ENTREGA",S=()=>{const c=a.payment_method||"pix";return{pix:"💠 PIX",credit_card:"💳 Crédito",debit_card:"💳 Débito",cash:"💵 Dinheiro",card:"💳 Cartão",mercadopago:"💠 Mercado Pago"}[c]||c.toUpperCase()},A=()=>{const s=a.payment_status||"pending";return{pending:"⏳ AGUARDANDO",paid:"✅ PAGO",failed:"❌ FALHOU",refunded:"↩️ REEMBOLSADO"}[s]||s.toUpperCase()},C=Number(a.subtotal||a.total||0),w=Number(a.delivery_fee||a.taxa_entrega||0),_=Number(a.discount||a.desconto||0),O=Number(a.total||0),N=l?.storeName||"PASTITA",R=l?.storePhone||"(63) 9117-2166",P=l?.storeAddress||"Palmas - TO",b=a.items?.map(s=>{const c=s,o=c.variant_name,x=c.notes,r=s.total_price||s.quantity*Number(s.unit_price);return`
      <tr>
        <td class="item-qty">${s.quantity}x</td>
        <td class="item-name">
          ${s.product_name}
          ${o?`<br><small>${o}</small>`:""}
          ${x?`<br><small class="item-notes">📝 ${x}</small>`:""}
        </td>
        <td class="item-price">${t(r)}</td>
      </tr>
    `}).join("")||"",h=a,$=h.customer_notes||h.observacoes||h.delivery_notes,E=$?`
      <div class="notes-section">
        <div class="notes-title">📝 OBSERVAÇÕES</div>
        <div class="notes-text">${$}</div>
      </div>
    `:"",i=`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="UTF-8">
        <title>Pedido #${a.order_number}</title>
        <style>
          @page {
            size: 80mm auto;
            margin: 0;
          }
          
          @media print {
            html, body {
              width: 80mm;
              margin: 0;
              padding: 0;
            }
          }
          
          * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
          }
          
          body {
            width: 80mm;
            max-width: 80mm;
            font-family: 'Lucida Console', 'Courier New', monospace;
            font-size: 12px;
            line-height: 1.4;
            padding: 3mm;
            color: #000;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          
          /* ===== HEADER ===== */
          .header {
            text-align: center;
            padding-bottom: 10px;
            margin-bottom: 8px;
            border-bottom: 2px dashed #000;
          }
          
          .store-name {
            font-size: 22px;
            font-weight: 900;
            letter-spacing: 2px;
            text-transform: uppercase;
          }
          
          .store-info {
            font-size: 11px;
            font-weight: 600;
            margin-top: 4px;
          }
          
          /* ===== ORDER NUMBER ===== */
          .order-header {
            background: #000;
            color: #fff;
            text-align: center;
            padding: 8px 4px;
            margin: 8px 0;
          }
          
          .order-number {
            font-size: 20px;
            font-weight: 900;
            letter-spacing: 1px;
          }
          
          .order-date {
            font-size: 11px;
            font-weight: 600;
            margin-top: 4px;
          }
          
          .delivery-badge {
            display: inline-block;
            font-size: 12px;
            font-weight: 800;
            margin-top: 6px;
            padding: 2px 8px;
            background: #fff;
            color: #000;
          }
          
          /* ===== SECTIONS ===== */
          .section {
            margin: 10px 0;
            padding: 8px 0;
            border-bottom: 1px dashed #000;
          }
          
          .section-title {
            font-size: 12px;
            font-weight: 900;
            text-transform: uppercase;
            margin-bottom: 6px;
            letter-spacing: 1px;
          }
          
          /* ===== CUSTOMER ===== */
          .customer-name {
            font-size: 14px;
            font-weight: 800;
          }
          
          .customer-phone {
            font-size: 13px;
            font-weight: 700;
            margin-top: 2px;
          }
          
          .customer-address {
            font-size: 11px;
            font-weight: 600;
            margin-top: 6px;
            padding: 6px;
            background: #f0f0f0;
            border: 1px solid #000;
          }
          
          .address-label {
            font-weight: 900;
            font-size: 10px;
            text-transform: uppercase;
          }
          
          /* ===== ITEMS TABLE ===== */
          .items-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 11px;
          }
          
          .items-table td {
            padding: 4px 2px;
            vertical-align: top;
            font-weight: 700;
          }
          
          .item-qty {
            width: 25px;
            font-weight: 900;
            font-size: 12px;
          }
          
          .item-name {
            font-weight: 700;
          }
          
          .item-name small {
            font-size: 9px;
            font-weight: 600;
            color: #333;
          }
          
          .item-notes {
            font-style: italic;
          }
          
          .item-price {
            width: 70px;
            text-align: right;
            font-weight: 800;
          }
          
          /* ===== TOTALS ===== */
          .totals-section {
            margin: 10px 0;
            padding: 8px 0;
          }
          
          .total-row {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            font-size: 12px;
            font-weight: 700;
          }
          
          .total-row.discount {
            color: #000;
          }
          
          .grand-total {
            display: flex;
            justify-content: space-between;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 3px double #000;
            font-size: 16px;
            font-weight: 900;
          }
          
          /* ===== PAYMENT ===== */
          .payment-section {
            background: #f5f5f5;
            padding: 8px;
            margin: 8px 0;
            border: 1px solid #000;
          }
          
          .payment-row {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            font-weight: 700;
            padding: 2px 0;
          }
          
          .payment-status {
            font-weight: 900;
            font-size: 13px;
          }
          
          /* ===== NOTES ===== */
          .notes-section {
            margin: 10px 0;
            padding: 8px;
            background: #fff8dc;
            border: 2px solid #000;
          }
          
          .notes-title {
            font-size: 11px;
            font-weight: 900;
            margin-bottom: 4px;
          }
          
          .notes-text {
            font-size: 11px;
            font-weight: 700;
            font-style: italic;
          }
          
          /* ===== FOOTER ===== */
          .footer {
            text-align: center;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 2px dashed #000;
          }
          
          .footer-thanks {
            font-size: 13px;
            font-weight: 800;
          }
          
          .footer-divider {
            font-size: 10px;
            margin: 6px 0;
            letter-spacing: -1px;
          }
          
          .footer-time {
            font-size: 9px;
            font-weight: 600;
          }
          
          /* ===== UTILITIES ===== */
          .text-center { text-align: center; }
          .text-right { text-align: right; }
          .bold { font-weight: 900; }
        </style>
      </head>
      <body>
        <!-- Header -->
        <div class="header">
          <div class="store-name">🍝 ${N}</div>
          <div class="store-info">${R}</div>
          <div class="store-info">${P}</div>
        </div>

        <!-- Order Info -->
        <div class="order-header">
          <div class="order-number">PEDIDO #${a.order_number}</div>
          <div class="order-date">${j(a.created_at)}</div>
          <div class="delivery-badge">${z()}</div>
        </div>

        <!-- Customer Info -->
        <div class="section">
          <div class="section-title">👤 CLIENTE</div>
          <div class="customer-name">${a.customer_name||h.cliente_nome||""}</div>
          <div class="customer-phone">📞 ${a.customer_phone||h.cliente_telefone||""}</div>
          ${k()?`
            <div class="customer-address">
              <div class="address-label">📍 Endereço de Entrega:</div>
              ${k()}
            </div>
          `:""}
        </div>

        <!-- Items -->
        <div class="section">
          <div class="section-title">🛒 ITENS DO PEDIDO</div>
          <table class="items-table">
            ${b}
          </table>
        </div>

        <!-- Totals -->
        <div class="totals-section">
          <div class="total-row">
            <span>Subtotal:</span>
            <span>${t(C)}</span>
          </div>
          ${w>0?`
            <div class="total-row">
              <span>Taxa de Entrega:</span>
              <span>${t(w)}</span>
            </div>
          `:""}
          ${_>0?`
            <div class="total-row discount">
              <span>Desconto:</span>
              <span>- ${t(_)}</span>
            </div>
          `:""}
          <div class="grand-total">
            <span>TOTAL:</span>
            <span>${t(O)}</span>
          </div>
        </div>

        <!-- Payment Info -->
        <div class="payment-section">
          <div class="payment-row">
            <span>Forma de Pagamento:</span>
            <span>${S()}</span>
          </div>
          <div class="payment-row">
            <span>Status:</span>
            <span class="payment-status">${A()}</span>
          </div>
        </div>

        ${E}

        <!-- Footer -->
        <div class="footer">
          <div class="footer-thanks">😋 Obrigado pela preferência!</div>
          <div class="footer-divider">════════════════════════════════</div>
          <div class="footer-time">Impresso em ${new Date().toLocaleString("pt-BR")}</div>
        </div>
      </body>
      </html>
    `;p.open(),p.write(i),p.close(),setTimeout(()=>{n.contentWindow?.focus(),n.contentWindow?.print()},300)},[])}},I=[{id:"pending",label:"Pendente",icon:F,color:"yellow"},{id:"confirmed",label:"Confirmado",icon:D,color:"blue"},{id:"preparing",label:"Preparando",icon:F,color:"orange"},{id:"ready",label:"Pronto",icon:D,color:"purple"},{id:"out_for_delivery",label:"Em Entrega",icon:ee,color:"indigo"},{id:"delivered",label:"Entregue",icon:te,color:"green"}],B={pending:{bg:"bg-yellow-50",text:"text-yellow-700",border:"border-yellow-200"},confirmed:{bg:"bg-blue-50",text:"text-blue-700",border:"border-blue-200"},paid:{bg:"bg-blue-50",text:"text-blue-700",border:"border-blue-200"},preparing:{bg:"bg-orange-50",text:"text-orange-700",border:"border-orange-200"},processing:{bg:"bg-orange-50",text:"text-orange-700",border:"border-orange-200"},ready:{bg:"bg-purple-50",text:"text-purple-700",border:"border-purple-200"},out_for_delivery:{bg:"bg-indigo-50",text:"text-indigo-700",border:"border-indigo-200"},shipped:{bg:"bg-indigo-50",text:"text-indigo-700",border:"border-indigo-200"},delivered:{bg:"bg-green-50",text:"text-green-700",border:"border-green-200"},completed:{bg:"bg-green-50",text:"text-green-700",border:"border-green-200"},cancelled:{bg:"bg-red-50",text:"text-red-700",border:"border-red-200"}},ne={pending:"Pendente",confirmed:"Confirmado",paid:"Pago",preparing:"Preparando",processing:"Processando",ready:"Pronto",out_for_delivery:"Em Entrega",shipped:"Enviado",delivered:"Entregue",completed:"Concluído",cancelled:"Cancelado"},v=d=>`R$ ${(d??0).toLocaleString("pt-BR",{minimumFractionDigits:2})}`,oe=d=>{const g=d.toLowerCase(),a=I.findIndex(l=>l.id===g||g==="paid"&&l.id==="confirmed"||g==="processing"&&l.id==="preparing"||g==="shipped"&&l.id==="out_for_delivery"||g==="completed"&&l.id==="delivered");return a>=0?a:0},ie=({currentStatus:d,isCancelled:g})=>{const a=oe(d);return g?e.jsx("div",{className:"flex items-center justify-center py-6",children:e.jsxs("div",{className:"flex items-center gap-3 px-6 py-3 bg-red-50 rounded-full",children:[e.jsx(U,{className:"w-6 h-6 text-red-500"}),e.jsx("span",{className:"text-lg font-semibold text-red-700 dark:text-red-300",children:"Pedido Cancelado"})]})}):e.jsx("div",{className:"py-6",children:e.jsxs("div",{className:"flex items-center justify-between relative",children:[e.jsx("div",{className:"absolute left-0 right-0 top-1/2 h-1 bg-gray-200 -translate-y-1/2 z-0"}),e.jsx("div",{className:"absolute left-0 top-1/2 h-1 bg-primary-500 -translate-y-1/2 z-0 transition-all duration-500",style:{width:`${a/(I.length-1)*100}%`}}),I.map((l,n)=>{const p=n<=a,j=n===a,t=l.icon;return e.jsxs("div",{className:"relative z-10 flex flex-col items-center",children:[e.jsx("div",{className:`
                  w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300
                  ${p?"bg-primary-500 text-white shadow-lg shadow-primary-500/30":"bg-white border-2 border-gray-200 text-gray-400"}
                  ${j?"ring-4 ring-primary-100 scale-110":""}
                `,children:p&&n<a?e.jsx(D,{className:"w-5 h-5"}):e.jsx(t,{className:"w-5 h-5"})}),e.jsx("span",{className:`
                  mt-2 text-xs font-medium whitespace-nowrap
                  ${p?"text-primary-600":"text-gray-400"}
                `,children:l.label})]},l.id)})]})})},he=()=>{const{id:d,storeId:g}=H(),a=q(),{printOrder:l}=re(),{store:n}=W(),p=g||n?.slug||n?.id||null,j=p?`/stores/${p}/orders`:"/stores",[t,k]=u.useState(null),[z,S]=u.useState([]),[A,C]=u.useState(!0),[w,_]=u.useState(null),[O,N]=u.useState(!1);u.useEffect(()=>{d&&R()},[d]);const R=async()=>{if(d){C(!0);try{const[r,m]=await Promise.all([f.getOrder(d),X.getByOrder(d).catch(()=>[])]);k(r),S(m)}catch(r){T.error(L(r)),a(j)}finally{C(!1)}}},P=async r=>{if(t){_(r);try{let m;switch(r){case"confirm":m=await f.confirmOrder(t.id);break;case"prepare":m=await f.startPreparing(t.id);break;case"ready":m=await f.markReady(t.id);break;case"deliver":m=await f.markOutForDelivery(t.id);break;case"complete":m=await f.deliverOrder(t.id);break;case"cancel":m=await f.cancelOrder(t.id),N(!1);break;default:return}k(m),T.success("Status atualizado!")}catch(m){T.error(L(m))}finally{_(null)}}},b=u.useMemo(()=>{if(!t)return null;const r=t.status.toLowerCase();return{pending:{action:"confirm",label:"Confirmar Pedido",color:"bg-blue-500 hover:bg-blue-600"},confirmed:{action:"prepare",label:"Iniciar Preparo",color:"bg-orange-500 hover:bg-orange-600"},paid:{action:"prepare",label:"Iniciar Preparo",color:"bg-orange-500 hover:bg-orange-600"},preparing:{action:"ready",label:"Marcar como Pronto",color:"bg-purple-500 hover:bg-purple-600"},processing:{action:"ready",label:"Marcar como Pronto",color:"bg-purple-500 hover:bg-purple-600"},ready:{action:"deliver",label:"Saiu para Entrega",color:"bg-indigo-500 hover:bg-indigo-600"},out_for_delivery:{action:"complete",label:"Marcar Entregue",color:"bg-green-500 hover:bg-green-600"},shipped:{action:"complete",label:"Marcar Entregue",color:"bg-green-500 hover:bg-green-600"}}[r]||null},[t]),h=t?.status.toLowerCase()==="cancelled",$=["delivered","completed"].includes(t?.status.toLowerCase()||"");if(A||!t)return e.jsx(G,{});const E=B[t.status.toLowerCase()]||B.pending,i=t.delivery_address||t.shipping_address,s=t.payment_status||"pending",c={pending:"Pendente",processing:"Processando",paid:"Pago",failed:"Falhou",refunded:"Reembolsado"},o={pix:"PIX",credit_card:"Cartão de Crédito",debit_card:"Cartão de Débito",cash:"Dinheiro",card:"Cartão",mercadopago:"Mercado Pago"},x=t.pix_ticket_url||t.payment_url||t.payment_link||t.init_point||null;return e.jsxs("div",{className:"min-h-screen bg-gray-50 dark:bg-black",children:[e.jsx("div",{className:"bg-white dark:bg-zinc-900 border-b sticky top-0 z-10",children:e.jsx("div",{className:"max-w-5xl mx-auto px-4 py-4",children:e.jsxs("div",{className:"flex items-center justify-between",children:[e.jsxs("div",{className:"flex items-center gap-4",children:[e.jsx("button",{onClick:()=>a(j),className:"p-2 hover:bg-gray-100 dark:hover:bg-zinc-700 dark:bg-gray-700 rounded-lg transition-colors",children:e.jsx(V,{className:"w-5 h-5 text-gray-600 dark:text-zinc-400"})}),e.jsxs("div",{children:[e.jsxs("h1",{className:"text-xl font-bold text-gray-900 dark:text-white",children:["Pedido #",t.order_number]}),e.jsx("p",{className:"text-sm text-gray-500 dark:text-zinc-400",children:ae(new Date(t.created_at),"dd 'de' MMMM 'às' HH:mm",{locale:se})})]})]}),e.jsx("div",{className:"flex items-center gap-2",children:e.jsx("span",{className:`px-4 py-2 rounded-full text-sm font-semibold ${E.bg} ${E.text}`,children:ne[t.status.toLowerCase()]||t.status})})]})})}),e.jsxs("div",{className:"max-w-5xl mx-auto px-4 py-6 space-y-6",children:[e.jsxs(y,{className:"p-6",children:[e.jsx(ie,{currentStatus:t.status,isCancelled:h}),b&&!h&&!$&&e.jsx("div",{className:"flex justify-center pt-4 border-t",children:e.jsx("button",{onClick:()=>P(b.action),disabled:!!w,className:`
                  px-8 py-3 rounded-xl text-white font-semibold text-lg
                  transition-all duration-200 transform hover:scale-105
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${b.color}
                `,children:w===b.action?e.jsxs("span",{className:"flex items-center gap-2",children:[e.jsxs("svg",{className:"animate-spin h-5 w-5",viewBox:"0 0 24 24",children:[e.jsx("circle",{className:"opacity-25",cx:"12",cy:"12",r:"10",stroke:"currentColor",strokeWidth:"4",fill:"none"}),e.jsx("path",{className:"opacity-75",fill:"currentColor",d:"M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"})]}),"Processando..."]}):b.label})})]}),e.jsxs("div",{className:"grid grid-cols-1 lg:grid-cols-3 gap-6",children:[e.jsxs("div",{className:"lg:col-span-2 space-y-6",children:[e.jsxs(y,{className:"p-6",children:[e.jsx("h2",{className:"text-lg font-semibold text-gray-900 dark:text-white mb-4",children:"Itens do Pedido"}),e.jsx("div",{className:"space-y-3",children:t.items?.map((r,m)=>e.jsxs("div",{className:"flex items-center justify-between py-3 border-b border-gray-100 last:border-0",children:[e.jsxs("div",{className:"flex items-center gap-4",children:[e.jsx("div",{className:"w-12 h-12 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center text-lg",children:"🍝"}),e.jsxs("div",{children:[e.jsx("p",{className:"font-medium text-gray-900 dark:text-white",children:r.product_name}),e.jsxs("p",{className:"text-sm text-gray-500 dark:text-zinc-400",children:[r.quantity,"x ",v(r.unit_price)]})]})]}),e.jsx("p",{className:"font-semibold text-gray-900 dark:text-white",children:v(r.subtotal||r.total_price)})]},r.id||m))}),e.jsxs("div",{className:"mt-6 pt-4 border-t border-gray-200 dark:border-zinc-800 space-y-2",children:[e.jsxs("div",{className:"flex justify-between text-gray-600 dark:text-zinc-400",children:[e.jsx("span",{children:"Subtotal"}),e.jsx("span",{children:v(t.subtotal)})]}),t.delivery_fee||t.shipping_cost?e.jsxs("div",{className:"flex justify-between text-gray-600 dark:text-zinc-400",children:[e.jsx("span",{children:"Entrega"}),e.jsx("span",{children:v(t.delivery_fee||t.shipping_cost)})]}):null,t.discount?e.jsxs("div",{className:"flex justify-between text-green-600 dark:text-green-400",children:[e.jsx("span",{children:"Desconto"}),e.jsxs("span",{children:["-",v(t.discount)]})]}):null,e.jsxs("div",{className:"flex justify-between text-xl font-bold text-gray-900 dark:text-white pt-2",children:[e.jsx("span",{children:"Total"}),e.jsx("span",{children:v(t.total)})]})]})]}),t.notes&&e.jsxs(y,{className:"p-6",children:[e.jsx("h2",{className:"text-lg font-semibold text-gray-900 dark:text-white mb-2",children:"Observações"}),e.jsx("p",{className:"text-gray-600 dark:text-zinc-400 bg-yellow-50 p-4 rounded-lg border border-yellow-100",children:t.notes})]})]}),e.jsxs("div",{className:"space-y-6",children:[e.jsxs(y,{className:"p-6",children:[e.jsx("h2",{className:"text-lg font-semibold text-gray-900 dark:text-white mb-4",children:"Cliente"}),e.jsxs("div",{className:"space-y-4",children:[e.jsxs("div",{className:"flex items-center gap-3",children:[e.jsx("div",{className:"w-12 h-12 bg-primary-100 rounded-full flex items-center justify-center",children:e.jsx("span",{className:"text-lg font-semibold text-primary-600",children:(t.customer_name||"C")[0].toUpperCase()})}),e.jsx("div",{children:e.jsx("p",{className:"font-semibold text-gray-900 dark:text-white",children:t.customer_name||"Cliente"})})]}),t.customer_phone&&e.jsxs("a",{href:`tel:${t.customer_phone}`,className:"flex items-center gap-3 p-3 bg-gray-50 dark:bg-black rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-800 transition-colors",children:[e.jsx(Y,{className:"w-5 h-5 text-gray-400"}),e.jsx("span",{className:"text-gray-700 dark:text-zinc-300",children:t.customer_phone})]}),t.customer_email&&e.jsxs("a",{href:`mailto:${t.customer_email}`,className:"flex items-center gap-3 p-3 bg-gray-50 dark:bg-black rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-800 transition-colors",children:[e.jsx(Z,{className:"w-5 h-5 text-gray-400"}),e.jsx("span",{className:"text-gray-700 dark:text-zinc-300 text-sm truncate",children:t.customer_email})]})]})]}),i&&Object.keys(i).length>0&&e.jsxs(y,{className:"p-6",children:[e.jsx("h2",{className:"text-lg font-semibold text-gray-900 dark:text-white mb-4",children:"Entrega"}),e.jsxs("div",{className:"flex items-start gap-3",children:[e.jsx(J,{className:"w-5 h-5 text-gray-400 mt-0.5"}),e.jsxs("div",{className:"text-gray-700 dark:text-zinc-300",children:[e.jsxs("p",{className:"font-medium",children:[i.street||i.address,i.number&&`, ${i.number}`]}),i.complement&&e.jsx("p",{className:"text-sm text-gray-500 dark:text-zinc-400",children:i.complement}),e.jsxs("p",{className:"text-sm",children:[i.neighborhood&&`${i.neighborhood}, `,i.city," - ",i.state]}),e.jsxs("p",{className:"text-sm text-gray-500 dark:text-zinc-400",children:["CEP: ",i.zip_code||i.cep]})]})]})]}),e.jsxs(y,{className:"p-6",children:[e.jsx("h2",{className:"text-lg font-semibold text-gray-900 dark:text-white mb-4",children:"Pagamento"}),z.length>0?e.jsx("div",{className:"space-y-3",children:z.map(r=>e.jsxs("div",{className:"p-3 bg-gray-50 dark:bg-black rounded-lg",children:[e.jsxs("div",{className:"flex items-center justify-between",children:[e.jsx("span",{className:"font-medium text-gray-900 dark:text-white",children:r.payment_method==="pix"?"💠 PIX":r.payment_method==="credit_card"?"💳 Cartão":r.payment_method==="cash"?"💵 Dinheiro":r.payment_method}),e.jsx("span",{className:`text-sm font-medium ${["paid","approved","completed"].includes(r.status)?"text-green-600":"text-yellow-600"}`,children:["paid","approved","completed"].includes(r.status)?"✓ Pago":"⏳ Pendente"})]}),e.jsx("p",{className:"text-lg font-bold text-gray-900 dark:text-white mt-1",children:v(r.amount)})]},r.id))}):e.jsxs("div",{className:"space-y-3",children:[e.jsxs("div",{className:"flex items-center justify-between",children:[e.jsx("span",{className:"text-sm text-gray-500 dark:text-zinc-400",children:"Método"}),e.jsx("span",{className:"font-medium text-gray-900 dark:text-white",children:o[t.payment_method||""]||t.payment_method||"-"})]}),e.jsxs("div",{className:"flex items-center justify-between",children:[e.jsx("span",{className:"text-sm text-gray-500 dark:text-zinc-400",children:"Status"}),e.jsx("span",{className:`text-sm font-semibold ${s==="paid"?"text-green-600":s==="failed"?"text-red-600":"text-yellow-600"}`,children:c[s]||s})]}),t.pix_code&&e.jsxs("div",{className:"text-xs text-gray-500 dark:text-zinc-400 break-all bg-gray-50 dark:bg-black rounded-lg p-3",children:[e.jsx("span",{className:"font-semibold text-gray-700 dark:text-zinc-300",children:"PIX:"})," ",t.pix_code]}),x&&e.jsx("a",{href:x,target:"_blank",rel:"noreferrer",className:"inline-flex items-center justify-center w-full px-4 py-2 rounded-lg bg-primary-50 text-primary-700 hover:bg-primary-100 transition-colors",children:"Abrir link de pagamento"})]})]}),e.jsxs(y,{className:"p-6",children:[e.jsx("h2",{className:"text-lg font-semibold text-gray-900 dark:text-white mb-4",children:"Ações"}),e.jsxs("div",{className:"space-y-2",children:[e.jsxs("button",{onClick:()=>l(t,{storeName:n?.name||t.store_name||"Loja",storePhone:n?.phone||n?.whatsapp_number||"",storeAddress:n?.address&&n?.city&&n?.state?`${n.address} - ${n.city}/${n.state}`:n?.address||n?.city||n?.state||""}),className:"w-full flex items-center justify-center gap-2 px-4 py-3 bg-primary-50 hover:bg-primary-100 rounded-lg transition-colors text-primary-700 font-medium",children:[e.jsx(K,{className:"w-5 h-5"}),"🖨️ Imprimir Pedido"]}),!h&&!$&&e.jsxs("button",{onClick:()=>N(!0),className:"w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-50 hover:bg-red-100 dark:bg-red-900/40 rounded-lg transition-colors text-red-600 dark:text-red-400",children:[e.jsx(U,{className:"w-5 h-5"}),"Cancelar Pedido"]})]})]})]})]})]}),e.jsx(Q,{isOpen:O,onClose:()=>N(!1),title:"Cancelar Pedido",children:e.jsxs("div",{className:"space-y-4",children:[e.jsxs("p",{className:"text-gray-600 dark:text-zinc-400",children:["Tem certeza que deseja cancelar o pedido ",e.jsxs("strong",{children:["#",t.order_number]}),"?"]}),e.jsx("p",{className:"text-sm text-red-600 dark:text-red-400",children:"Esta ação não pode ser desfeita."}),e.jsxs("div",{className:"flex justify-end gap-3 pt-4",children:[e.jsx(M,{variant:"secondary",onClick:()=>N(!1),children:"Voltar"}),e.jsx(M,{variant:"danger",onClick:()=>P("cancel"),isLoading:w==="cancel",children:"Confirmar Cancelamento"})]})]})})]})};export{he as OrderDetailPageNew,he as default};
