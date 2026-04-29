from unittest.mock import patch

from django.test import SimpleTestCase

from apps.agents.services import LangchainService
from apps.core.auth.whatsapp_auth import WhatsAppAuthService
from apps.whatsapp.tasks import send_agent_response


class AgentRuntimeGuardsTestCase(SimpleTestCase):
    def _make_service(self):
        service = LangchainService.__new__(LangchainService)
        service.agent = None
        return service

    def test_direct_reply_for_generic_order_with_pix(self):
        service = self._make_service()
        reply = service._get_direct_runtime_reply("quero 2 saladas e pagar no pix", store=None)
        self.assertIsNotNone(reply)
        self.assertIn("Primeiro me diga quais itens", reply)
        self.assertIn("PIX", reply)

    def test_no_direct_reply_for_delivery_question(self):
        service = self._make_service()
        reply = service._get_direct_runtime_reply("qual taxa de entrega?", store=None)
        self.assertIsNone(reply)

    def test_allowed_tools_for_delivery(self):
        service = self._make_service()
        self.assertEqual(service._resolve_allowed_tools("qual taxa de entrega?"), {'informacoes_entrega'})

    def test_allowed_tools_for_payment(self):
        service = self._make_service()
        self.assertEqual(service._resolve_allowed_tools("me manda o pix"), {'consultar_pagamento'})

    def test_auth_template_configs_do_not_inject_button_payload(self):
        config = WhatsAppAuthService._get_template_configs("123456")[0]

        self.assertEqual(config["name"], "codigo_verificacao")
        self.assertEqual(
            config["components"],
            [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "123456"},
                    ],
                }
            ],
        )

    @patch("apps.whatsapp.services.MessageService")
    def test_send_agent_response_routes_template_payload(self, mock_message_service):
        service_instance = mock_message_service.return_value

        send_agent_response.run(
            account_id="11111111-1111-1111-1111-111111111111",
            to="556399547790",
            response_text="123456",
            reply_to="msg-1",
            response_source="ai_agent",
            whatsapp_response={
                "type": "template",
                "template_name": "codigo_verificacao",
                "language_code": "pt_BR",
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": "123456"},
                        ],
                    }
                ],
            },
        )

        service_instance.send_template_message.assert_called_once()
        kwargs = service_instance.send_template_message.call_args.kwargs
        self.assertEqual(kwargs["template_name"], "codigo_verificacao")
        self.assertEqual(kwargs["components"][0]["parameters"][0]["text"], "123456")
