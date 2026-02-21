import{a as r,l as i}from"./feature-automation-CLWK1V5x.js";const o="/marketing",d={coupon:{name:"Cupom de Desconto",subject:"🎁 Presente especial para você: {{discount_value}}% OFF!",template_type:"coupon",variables:["customer_name","coupon_code","discount_value","expiry_date","store_name"],html_content:`
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cupom de Desconto</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
          <!-- Header -->
          <tr>
            <td style="background: linear-gradient(135deg, #722F37 0%, #8B3A42 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0; font-size: 28px;">🎁 Presente Especial!</h1>
            </td>
          </tr>
          <!-- Content -->
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333; margin: 0 0 20px;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6; margin: 0 0 30px;">
                Preparamos um desconto exclusivo para você aproveitar em sua próxima compra na <strong>{{store_name}}</strong>!
              </p>
              <!-- Coupon Box -->
              <div style="background: linear-gradient(135deg, #722F37 0%, #8B3A42 100%); border-radius: 12px; padding: 30px; text-align: center; margin: 30px 0;">
                <p style="color: #ffffff; font-size: 14px; margin: 0 0 10px; text-transform: uppercase; letter-spacing: 2px;">Seu cupom</p>
                <p style="color: #ffffff; font-size: 36px; font-weight: bold; margin: 0; letter-spacing: 4px;">{{coupon_code}}</p>
                <p style="color: #ffffff; font-size: 48px; font-weight: bold; margin: 20px 0 0;">{{discount_value}}% OFF</p>
              </div>
              <p style="font-size: 14px; color: #999; text-align: center; margin: 20px 0;">
                Válido até: <strong>{{expiry_date}}</strong>
              </p>
              <!-- CTA Button -->
              <div style="text-align: center; margin: 30px 0;">
                <a href="{{store_url}}" style="display: inline-block; background: #722F37; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                  Usar Meu Cupom
                </a>
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color: #f8f8f8; padding: 30px; text-align: center;">
              <p style="font-size: 12px; color: #999; margin: 0;">
                © {{year}} {{store_name}}. Todos os direitos reservados.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim()},welcome:{name:"Boas-vindas",subject:"👋 Bem-vindo(a) à {{store_name}}!",template_type:"welcome",variables:["customer_name","store_name","store_url"],html_content:`
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden;">
          <tr>
            <td style="background: linear-gradient(135deg, #722F37 0%, #8B3A42 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0;">👋 Bem-vindo(a)!</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                É um prazer ter você conosco! Agora você faz parte da família <strong>{{store_name}}</strong>.
              </p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                Prepare-se para receber ofertas exclusivas, novidades e muito mais!
              </p>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{{store_url}}" style="display: inline-block; background: #722F37; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                  Conhecer a Loja
                </a>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim()},promotion:{name:"Promoção",subject:"🔥 {{promotion_title}} - Só por tempo limitado!",template_type:"promotional",variables:["customer_name","promotion_title","promotion_description","store_name","store_url"],html_content:`
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden;">
          <tr>
            <td style="background: linear-gradient(135deg, #FF6B6B 0%, #FF8E53 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0; font-size: 32px;">🔥 PROMOÇÃO!</h1>
              <p style="color: #ffffff; font-size: 24px; margin: 10px 0 0;">{{promotion_title}}</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                {{promotion_description}}
              </p>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{{store_url}}" style="display: inline-block; background: linear-gradient(135deg, #FF6B6B 0%, #FF8E53 100%); color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                  Aproveitar Agora
                </a>
              </div>
              <p style="font-size: 12px; color: #999; text-align: center;">
                *Promoção por tempo limitado. Sujeito a disponibilidade.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim()},order_confirmation:{name:"Confirmação de Pedido",subject:"✅ Pedido #{{order_number}} confirmado!",template_type:"order_confirmation",variables:["customer_name","order_number","order_total","order_items","delivery_address","store_name"],html_content:`
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden;">
          <tr>
            <td style="background: linear-gradient(135deg, #10B981 0%, #059669 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0;">✅ Pedido Confirmado!</h1>
              <p style="color: #ffffff; font-size: 20px; margin: 10px 0 0;">#{{order_number}}</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                Seu pedido foi confirmado e está sendo preparado com carinho!
              </p>
              
              <div style="background: #f8f8f8; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <h3 style="margin: 0 0 15px; color: #333;">Resumo do Pedido</h3>
                {{order_items}}
                <hr style="border: none; border-top: 1px solid #ddd; margin: 15px 0;">
                <p style="font-size: 18px; font-weight: bold; color: #333; margin: 0;">
                  Total: R$ {{order_total}}
                </p>
              </div>

              <div style="background: #f8f8f8; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <h3 style="margin: 0 0 10px; color: #333;">📍 Endereço de Entrega</h3>
                <p style="color: #666; margin: 0;">{{delivery_address}}</p>
              </div>
            </td>
          </tr>
          <tr>
            <td style="background-color: #f8f8f8; padding: 30px; text-align: center;">
              <p style="font-size: 12px; color: #999; margin: 0;">
                Obrigado por comprar na {{store_name}}!
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim()},abandoned_cart:{name:"Carrinho Abandonado",subject:"🛒 Você esqueceu algo no carrinho!",template_type:"abandoned_cart",variables:["customer_name","cart_items","cart_total","store_name","store_url"],html_content:`
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 16px; overflow: hidden;">
          <tr>
            <td style="background: linear-gradient(135deg, #722F37 0%, #8B3A42 100%); padding: 40px; text-align: center;">
              <h1 style="color: #ffffff; margin: 0;">🛒 Esqueceu de algo?</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 40px;">
              <p style="font-size: 18px; color: #333;">Olá, <strong>{{customer_name}}</strong>!</p>
              <p style="font-size: 16px; color: #666; line-height: 1.6;">
                Notamos que você deixou alguns itens no carrinho. Eles ainda estão esperando por você!
              </p>
              
              <div style="background: #f8f8f8; border-radius: 8px; padding: 20px; margin: 20px 0;">
                {{cart_items}}
                <hr style="border: none; border-top: 1px solid #ddd; margin: 15px 0;">
                <p style="font-size: 18px; font-weight: bold; color: #333; margin: 0;">
                  Total: R$ {{cart_total}}
                </p>
              </div>

              <div style="text-align: center; margin: 30px 0;">
                <a href="{{store_url}}" style="display: inline-block; background: #722F37; color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-size: 16px; font-weight: bold;">
                  Ver Cardápio
                </a>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    `.trim()}},c=t=>t.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,""),l={async list(t){try{const e=await r.get(`${o}/templates/`,{params:{store:t}}),a=Array.isArray(e.data)?e.data:e.data.results||[];return a.length>0?a:l.getPresetTemplates(t)}catch(e){return i.warn("API not available, using preset templates",{error:String(e)}),l.getPresetTemplates(t)}},getPresetTemplates(t){return Object.entries(d).map(([e,a])=>({id:`preset-${e}`,store:t,name:a.name||e,slug:e,subject:a.subject||"",html_content:a.html_content||"",template_type:a.template_type||"custom",variables:a.variables||[],is_active:!0,created_at:new Date().toISOString(),updated_at:new Date().toISOString()}))},async get(t){return(await r.get(`${o}/templates/${t}/`)).data},async create(t){const e={...t,slug:t.slug||c(t.name)};return(await r.post(`${o}/templates/`,e)).data},async update(t,e){return(await r.patch(`${o}/templates/${t}/`,e)).data},async delete(t){await r.delete(`${o}/templates/${t}/`)},async preview(t,e){return(await r.post(`${o}/templates/${t}/preview/`,{variables:e})).data.html},async sendTest(t,e,a){await r.post(`${o}/templates/${t}/send-test/`,{email:e,variables:a})}},p={async list(t){try{const e=await r.get(`${o}/campaigns/`,{params:{store:t}});return Array.isArray(e.data)?e.data:e.data.results||[]}catch(e){return i.warn("Failed to fetch campaigns",{error:String(e)}),[]}},async get(t){return(await r.get(`${o}/campaigns/${t}/`)).data},async create(t){const e={...t};return(!e.template||e.template===null||typeof e.template=="string"&&(e.template.startsWith("preset-")||e.template===""))&&delete e.template,Object.keys(e).forEach(s=>{(e[s]===""||e[s]===void 0||e[s]===null)&&delete e[s]}),(await r.post(`${o}/campaigns/`,e)).data},async update(t,e){return(await r.patch(`${o}/campaigns/${t}/`,e)).data},async delete(t){await r.delete(`${o}/campaigns/${t}/`)},async send(t){return(await r.post(`${o}/campaigns/${t}/send/`)).data},async schedule(t,e){return(await r.post(`${o}/campaigns/${t}/schedule/`,{scheduled_at:e})).data},async pause(t){return(await r.post(`${o}/campaigns/${t}/pause/`)).data},async cancel(t){return(await r.post(`${o}/campaigns/${t}/cancel/`)).data},async getRecipients(t){return(await r.get(`${o}/campaigns/${t}/recipients/`)).data}},m={async list(t){return(await r.get("/campaigns/campaigns/",{params:{store:t}})).data},async get(t){return(await r.get(`/campaigns/campaigns/${t}/`)).data},async create(t){return(await r.post("/campaigns/campaigns/",t)).data},async update(t,e){return(await r.patch(`/campaigns/campaigns/${t}/`,e)).data},async delete(t){await r.delete(`/campaigns/campaigns/${t}/`)},async send(t){await r.post(`/campaigns/campaigns/${t}/start/`)}},g={async get(t){try{const a=(await r.get(`${o}/stats/`,{params:{store:t}})).data;return{email:{total_campaigns:a.campaigns?.total||0,total_sent:a.emails?.sent||0,total_delivered:a.emails?.delivered||0,total_opened:a.emails?.opened||0,total_clicked:a.emails?.clicked||0,open_rate:a.rates?.open_rate||0,click_rate:a.rates?.click_rate||0},whatsapp:{total_campaigns:0,total_sent:0,total_delivered:0,total_read:0,total_replied:0,delivery_rate:0,read_rate:0},subscribers:{total:a.subscribers?.total||0,active:a.subscribers?.active||0,unsubscribed:(a.subscribers?.total||0)-(a.subscribers?.active||0),new_this_month:a.subscribers?.new_last_30_days||0}}}catch(e){return i.warn("Error fetching marketing stats:",{error:String(e)}),{email:{total_campaigns:0,total_sent:0,total_delivered:0,total_opened:0,total_clicked:0,open_rate:0,click_rate:0},whatsapp:{total_campaigns:0,total_sent:0,total_delivered:0,total_read:0,total_replied:0,delivery_rate:0,read_rate:0},subscribers:{total:0,active:0,unsubscribed:0,new_this_month:0}}}}},u={async sendCouponEmail(t){try{return(await r.post(`${o}/actions/send_coupon/`,t)).data}catch(e){const a=e;return i.error("Failed to send coupon email",{error:String(e)}),{success:!1,error:a.response?.data?.error||"Erro ao enviar email"}}},async sendWelcomeEmail(t){try{return(await r.post(`${o}/actions/send_welcome/`,t)).data}catch(e){const a=e;return i.error("Failed to send welcome email",{error:String(e)}),{success:!1,error:a.response?.data?.error||"Erro ao enviar email"}}}},f={async list(t,e){try{const a={store:t};e?.status&&(a.status=e.status),e?.search&&(a.search=e.search);const s=await r.get(`${o}/customers/`,{params:a}),n=Array.isArray(s.data)?s.data:s.data.results||[];return i.info("Fetched customers",{count:n.length}),n}catch(a){i.warn("Failed to fetch customers, trying subscribers fallback",{error:String(a)});try{const s={store:t};e?.status&&(s.status=e.status);const n=await r.get(`${o}/subscribers/`,{params:s});return Array.isArray(n.data)?n.data:n.data.results||[]}catch{return[]}}},async count(t,e){try{const a={store:t};return e&&(a.status=e),(await r.get(`${o}/customers/count/`,{params:a})).data.count}catch{return(await this.list(t,{status:e})).length}},async create(t){return(await r.post(`${o}/subscribers/`,t)).data},async importCsv(t,e){return(await r.post(`${o}/subscribers/import_csv/`,{store:t,contacts:e})).data},async unsubscribe(t){return(await r.post(`${o}/subscribers/${t}/unsubscribe/`)).data}},h={emailTemplates:l,emailCampaigns:p,whatsappCampaigns:m,stats:g,quickActions:u,subscribers:f,presets:d},_={async list(t){try{const e=await r.get(`${o}/automations/`,{params:{store:t}});return Array.isArray(e.data)?e.data:e.data.results||[]}catch(e){return i.warn("Failed to fetch automations",{error:String(e)}),[]}},async get(t){try{return(await r.get(`${o}/automations/${t}/`)).data}catch{return null}},async create(t){return(await r.post(`${o}/automations/`,t)).data},async update(t,e){return(await r.patch(`${o}/automations/${t}/`,e)).data},async delete(t){await r.delete(`${o}/automations/${t}/`)},async toggle(t){return(await r.post(`${o}/automations/${t}/toggle/`)).data},async getTriggerTypes(){try{return(await r.get(`${o}/automations/trigger_types/`)).data}catch{return[{value:"new_user",label:"Novo Usuário"},{value:"welcome",label:"Boas-vindas"},{value:"order_confirmed",label:"Pedido Confirmado"},{value:"order_preparing",label:"Pedido em Preparo"},{value:"order_shipped",label:"Pedido Enviado"},{value:"order_delivered",label:"Pedido Entregue"},{value:"order_cancelled",label:"Pedido Cancelado"},{value:"payment_confirmed",label:"Pagamento Confirmado"},{value:"payment_failed",label:"Pagamento Falhou"},{value:"cart_abandoned",label:"Carrinho Abandonado"},{value:"coupon_sent",label:"Cupom Enviado"},{value:"birthday",label:"Aniversário"},{value:"review_request",label:"Solicitar Avaliação"}]}},async getLogs(t){try{return(await r.get(`${o}/automations/${t}/logs/`)).data}catch{return[]}},async test(t,e){return(await r.post(`${o}/automations/test/`,{automation_id:t,email:e})).data},async trigger(t,e,a,s,n){return(await r.post(`${o}/automations/trigger/`,{store:t,trigger_type:e,recipient_email:a,recipient_name:s||"",context:n||{}})).data}};export{_ as a,h as m};
