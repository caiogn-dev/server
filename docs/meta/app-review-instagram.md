# App Review do Instagram — o que enviar (21/set/2026)

App **Cardapidex** `2233885800471071`. Duas análises recusadas (abr e mai/2026),
ambas pedindo permissões demais de uma vez, do caminho do login do Facebook.

## Situação conferida pelo MCP em 21/set

| Item | Estado |
|---|---|
| Política de privacidade | ✅ https://cardapidex.com.br/privacidade |
| Termos de serviço | ✅ https://cardapidex.com.br/termos |
| Verificação de negócio | ✅ passa |
| E-mail de contato verificado | ❌ `contact_email_verified: false` |
| URL de exclusão de dados | ❌ vazia |
| Enviar agora | ❌ `can_submit: false` — "envio anterior em análise" |
| `instagram_business_basic` | recusada · no envio aberto · falta screencast + Data Use Checkup |
| `instagram_business_manage_messages` | recusada · no envio aberto · falta screencast + Data Use Checkup |
| `instagram_business_manage_comments` | recusada · **fora** do envio aberto |
| `instagram_basic` | **no envio aberto e não deve estar** — é do caminho do Facebook, nenhum código usa |

## Ordem

1. No rascunho ("Not submitted"), clicar em **customize use cases** e:
   - **tirar `instagram_basic`** das novas solicitações;
   - **acrescentar `instagram_business_manage_comments`**, que não está lá e é a
     permissão da promoção de comentário.
   O rascunho listado em 21/set trazia manage_messages + basic + instagram_basic,
   e NÃO trazia manage_comments — ou seja, pedia uma permissão que o código não
   usa e deixava de fora a que o produto precisa.
2. Configurações → Básico: verificar o e-mail e preencher a exclusão de dados com
   `https://backend.pastita.com.br/api/v1/instagram/data-deletion/` (POST-only, valida `signed_request`).
3. Data Use Checkup: https://developers.facebook.com/apps/2233885800471071/data-use-checkup/
4. Montar o envio com **exatamente três** permissões: `instagram_business_basic`,
   `instagram_business_manage_messages`, `instagram_business_manage_comments`.
   Remover `instagram_basic` e qualquer permissão de Página.
5. Conferir a parte "Existing access for renewal": `whatsapp_business_messaging`,
   `whatsapp_business_management` e `public_profile`. São as permissões que
   sustentam o WhatsApp em produção. Ver se dá para renovar em envio separado
   do pedido do Instagram, para não amarrar o que já funciona ao que pode cair.
6. Gravar UM screencast que mostre as três em uso, na ordem do roteiro abaixo.

## O que escrever em cada permissão (inglês, como a Meta pede)

**instagram_business_basic**
> Cardapidex is a SaaS used by restaurants in Brazil to run their menu, orders and
> customer messaging. After the merchant connects their own Instagram professional
> account with Instagram Login, we read the account id, username and profile
> picture to show which account is connected in the merchant dashboard, and we read
> the merchant's own media so they can attach a promotion to one of their posts.
> We do not read other people's accounts or media.

**instagram_business_manage_messages**
> The merchant runs comment promotions on their own posts ("comment CUPOM and get
> your coupon"). When a customer comments, we send that customer a single private
> reply with the coupon, using the comment id. The merchant also reads and answers
> those direct conversations from the Cardapidex inbox, inside the 24-hour window.
> Messages are only exchanged between the merchant's own account and people who
> contacted that account first.

**instagram_business_manage_comments**
> We read comments on the merchant's own posts to know who entered the promotion,
> and we post one public reply on the comment when the merchant configured one
> ("sent you a DM!"). Comments are used only to decide whether the commenter meets
> the promotion rules the merchant defined (keyword, number of tagged friends).

## Roteiro do screencast (um vídeo só, ~3 min, com narração ou legenda)

1. Painel → **Conexões**. Mostrar o cartão do Instagram desconectado.
2. Clicar em **Conectar Instagram** → tela de Login com Instagram → aceitar.
   *(mostra o consentimento e o retorno; cobre `instagram_business_basic`)*
3. De volta no painel, mostrar o @ da conta conectada no cartão.
4. Ir em **Marketing → Promoção no Instagram** → Nova promoção.
   Colar o link de um post real, palavra "EU QUERO", mensagem do direct, salvar.
   *(mostra a frase pronta para a legenda)*
5. No celular/segunda conta, comentar **EU QUERO** no post.
6. Mostrar a DM chegando na conta que comentou e a resposta pública no comentário.
   *(cobre `_manage_messages` e `_manage_comments`)*
7. Painel → a promoção mostrando "1 participando" e, se houver, quem ficou de fora
   com o motivo.
8. Inbox → aba **Direct**: abrir a conversa e responder.

## Credenciais de teste para o revisor

A Meta exige um acesso que o revisor use. Criar um usuário de demonstração no
painel (loja de teste, sem dados de cliente real) e informar usuário e senha no
formulário, junto do passo a passo acima em texto.

## Por que as anteriores caíram

As duas recusas pediam, no mesmo envio, `instagram_basic`, `instagram_manage_messages`,
`instagram_manage_comments`, `pages_show_list`, `pages_read_engagement` e
`business_management` — o conjunto do login do FACEBOOK, que exige Página e não
serve para loja cliente. O produto hoje não usa nenhuma delas (ver
`apps/instagram/services/login_instagram.py`). Pedir permissão que o app não
demonstra é motivo de recusa por si só.
