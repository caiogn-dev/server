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

## Roteiro do screencast (gravação de tela, ~3 min)

### Antes de apertar o rec
- Reconectar o Instagram em **Conexões** (a conta antiga tem token morto; o
  cartão mostra "Precisa reconectar"). Sem isso a grade de fotos vem vazia.
- Ter um **segundo perfil** no celular para comentar no post.
- Escolher o post que vai receber a promoção. Qualquer comentário nele vira DM
  automática enquanto a promoção estiver no ar.
- Navegador limpo: sem outras abas, sem extensão aparecendo, zoom em 100%.
- Gravar o **celular junto** (ou um segundo trecho) — é onde o revisor vê a DM
  chegar de verdade.

### Cena a cena

| # | Tela | O que mostrar | Cobre |
|---|---|---|---|
| 1 | Painel → Conexões | Cartão do Instagram desconectado | contexto |
| 2 | Clique em Conectar | Tela de login do Instagram, a **lista de permissões** e o botão de autorizar | consentimento |
| 3 | Volta ao painel | O @ da conta e o selo "Funcionando" | `instagram_business_basic` |
| 4 | Marketing → Promoção no Instagram → Nova promoção | A **grade com as fotos da conta** carregando | `instagram_business_basic` (leitura de mídia) |
| 5 | Clicar numa foto | Passo "o que o cliente faz": palavra EU QUERO, botão "Marcar amigos" | regra |
| 6 | Passo do prêmio | Escrever a mensagem do direct; mostrar a **prévia** com a frase da legenda | — |
| 7 | Colocar no ar | A promoção na lista, "0 participando" | — |
| 8 | Celular, outro perfil | Comentar **EU QUERO** no post | — |
| 9 | Celular | A **DM chegando** e a resposta pública no comentário | `_manage_messages` + `_manage_comments` |
| 10 | Painel, promoção | "1 participando"; se alguém comentou errado, o motivo | `_manage_comments` |
| 11 | Inbox → aba Direct | Abrir a conversa e **responder** | `_manage_messages` |

### Narração (ou legenda) por cena
- Cena 2: "The merchant authorizes their own Instagram professional account."
- Cena 4: "We read the merchant's own media so they can attach a promotion to one of their posts."
- Cena 9: "The customer who commented receives one private reply with the coupon."
- Cena 11: "The merchant answers that conversation from the Cardapidex inbox."

### Erros que derrubam a análise
- Cortar a tela de consentimento: o revisor precisa ver as permissões pedidas.
- Mostrar dado de cliente real (nome, telefone) — usar perfil de teste.
- Vídeo sem som e sem legenda: a Meta pede que dê para entender o fluxo.
- Mostrar telas de WhatsApp no meio: confunde o escopo do pedido.

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
