"""
Embedded Signup (Meta WhatsApp) — troca o `code` do fluxo de Embedded Signup
por um token, registra o número na Cloud API, inscreve o app na WABA, cria/atualiza
o WhatsAppAccount e VINCULA à loja (Store.whatsapp_account) — fazendo as respostas
e os disparos de status irem para a loja certa.

Fluxo (lado backend), modelado no sample oficial do Meta
(github.com/fbsamples/business-messaging-sample-tech-provider-app):
  1. exchange_code(code)            -> access_token (business integration token)
  2. fetch phone details            -> display_phone_number, verified_name
  3. register_number(pin)           -> habilita envio pela Cloud API
  4. subscribe_app(waba_id)         -> habilita webhooks de mensagem
  5. persist + link store
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class EmbeddedSignupError(Exception):
    pass


class EmbeddedSignupService:
    def __init__(self):
        self.base = settings.WHATSAPP_API_BASE_URL.rstrip('/')  # https://graph.facebook.com/vXX.0
        self.app_id = settings.META_APP_ID
        self.app_secret = settings.META_APP_SECRET

    # 1) code -> token
    def exchange_code(self, code: str) -> str:
        if not self.app_id or not self.app_secret:
            raise EmbeddedSignupError('META_APP_ID / META_APP_SECRET não configurados no .env')
        resp = requests.get(
            f'{self.base}/oauth/access_token',
            params={
                'client_id': self.app_id,
                'client_secret': self.app_secret,
                'code': code,
            },
            timeout=15,
        )
        data = resp.json()
        token = data.get('access_token')
        if not token:
            logger.error('Embedded Signup: falha na troca code->token: %s', data)
            raise EmbeddedSignupError("Falha ao trocar code por token")
        return token

    def _graph_get(self, path: str, token: str, params: dict = None) -> dict:
        resp = requests.get(f'{self.base}/{path}', params={**(params or {}), 'access_token': token}, timeout=15)
        return resp.json()

    def _graph_post(self, path: str, token: str, payload: dict = None) -> dict:
        resp = requests.post(
            f'{self.base}/{path}',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json=payload or {},
            timeout=15,
        )
        return resp.json()

    # 2) detalhes do número
    def fetch_phone(self, phone_number_id: str, token: str) -> dict:
        return self._graph_get(
            phone_number_id, token,
            params={'fields': 'display_phone_number,verified_name,quality_rating'},
        )

    # 3) registra o número (necessário antes de enviar)
    def register_number(self, phone_number_id: str, token: str, pin: str) -> dict:
        return self._graph_post(
            f'{phone_number_id}/register', token,
            payload={'messaging_product': 'whatsapp', 'pin': pin},
        )

    # 4) inscreve o app na WABA (webhooks de mensagem)
    def subscribe_app(self, waba_id: str, token: str) -> dict:
        return self._graph_post(f'{waba_id}/subscribed_apps', token)

    def onboard(self, *, code: str, waba_id: str, phone_number_id: str,
                store=None, owner=None, pin: str = '', account_name: str = '') -> 'WhatsAppAccount':
        """Executa o onboarding completo e devolve o WhatsAppAccount vinculado."""
        from apps.whatsapp.models import WhatsAppAccount

        token = self.exchange_code(code)
        phone = self.fetch_phone(phone_number_id, token)
        display = phone.get('display_phone_number', '')
        verified_name = phone.get('verified_name', '') or account_name

        # Coexistência (whatsapp_business_app_onboarding) não usa /register com PIN —
        # o número já está verificado pelo QR no app. Só registramos quando há PIN
        # (fluxo de migração com SMS).
        if pin:
            reg = self.register_number(phone_number_id, token, pin)
            if not reg.get('success') and 'error' in reg:
                logger.warning('register_number retornou: %s', reg)
        else:
            logger.info('Coexistence: sem PIN, pulando /register (número verificado via QR)')

        sub = self.subscribe_app(waba_id, token)
        logger.info('subscribe_app: %s', sub)

        acc, created = WhatsAppAccount.objects.get_or_create(
            phone_number_id=phone_number_id,
            defaults=dict(
                name=verified_name or display or 'WhatsApp',
                waba_id=waba_id,
                phone_number=(display or '').replace(' ', '').replace('+', '').replace('-', ''),
                display_phone_number=display,
                status=WhatsAppAccount.AccountStatus.ACTIVE,
                webhook_verify_token=settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN,
                owner=owner,
            ),
        )
        acc.access_token = token  # setter encripta
        acc.waba_id = waba_id
        acc.status = WhatsAppAccount.AccountStatus.ACTIVE
        # Reconexão de número já cadastrado precisa REATIVAR a conta: o
        # roteamento de mensagens recebidas filtra is_active=True.
        acc.is_active = True
        if owner and not acc.owner_id:
            acc.owner = owner
        acc.save()

        # VÍNCULO com a loja — chave da multi-tenancy (respostas + status por loja)
        if store is not None:
            store.whatsapp_account = acc
            store.save(update_fields=['whatsapp_account', 'updated_at'])

        logger.info('Embedded Signup OK: account=%s store=%s created=%s',
                    acc.id, getattr(store, 'slug', None), created)
        return acc
