"""
Management command to setup email automations for a store.
Usage: python manage.py setup_email_automations --store=pastita
"""
from django.core.management.base import BaseCommand
from apps.marketing.models import EmailAutomation
from apps.stores.models import Store


class Command(BaseCommand):
    help = 'Setup email automations for a store'

    def add_arguments(self, parser):
        parser.add_argument(
            '--store',
            type=str,
            default='pastita',
            help='Store slug (default: pastita)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreate automations even if they exist'
        )

    def handle(self, *args, **options):
        store_slug = options['store']
        force = options['force']

        try:
            store = Store.objects.get(slug=store_slug)
        except Store.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Store "{store_slug}" not found'))
            return

        self.stdout.write(f'Setting up email automations for {store.name}...')

        automations_data = [
            {
                'trigger_type': 'new_user',
                'name': 'Boas-vindas - Novo Cadastro',
                'subject': 'Bem-vindo à {{store_name}}, {{first_name}}! 🍝',
                'html_content': '''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#fff;">
<tr><td style="background:linear-gradient(135deg,#722F37,#8B3A44);padding:40px 20px;text-align:center;">
<h1 style="color:#fff;margin:0;font-size:28px;">🍝 Bem-vindo à {{store_name}}!</h1>
</td></tr>
<tr><td style="padding:40px 30px;">
<p style="font-size:18px;color:#333;">Olá, <strong>{{first_name}}</strong>!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Estamos muito felizes em ter você conosco! 🎉</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Na {{store_name}}, preparamos massas artesanais com muito carinho e ingredientes selecionados.</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Use o cupom <strong style="color:#722F37;">BEMVINDO10</strong> na sua primeira compra e ganhe 10% de desconto!</p>
<div style="text-align:center;margin:30px 0;">
<a href="https://pastita.com.br/cardapio" style="display:inline-block;background:#722F37;color:#fff;text-decoration:none;padding:16px 40px;border-radius:8px;font-size:16px;font-weight:bold;">Ver Cardápio →</a>
</div>
</td></tr>
<tr><td style="background:#f9f9f9;padding:30px;text-align:center;">
<p style="color:#999;font-size:12px;margin:0;">{{store_name}} - Massas Artesanais<br>Palmas - TO</p>
</td></tr>
</table>
</body>
</html>''',
                'delay_minutes': 0,
            },
            {
                'trigger_type': 'order_confirmed',
                'name': 'Pedido Confirmado',
                'subject': 'Pedido #{{order_number}} confirmado! 🎉',
                'html_content': '''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#fff;">
<tr><td style="background:linear-gradient(135deg,#722F37,#8B3A44);padding:40px 20px;text-align:center;">
<h1 style="color:#fff;margin:0;font-size:28px;">🍝 Pedido Confirmado!</h1>
</td></tr>
<tr><td style="padding:40px 30px;">
<p style="font-size:18px;color:#333;">Olá, <strong>{{customer_name}}</strong>!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Recebemos seu pedido e ele está sendo preparado com muito carinho!</p>
<div style="background:#f9f9f9;border-radius:12px;padding:20px;margin:20px 0;text-align:center;">
<p style="color:#722F37;font-size:14px;margin:0 0 10px;text-transform:uppercase;">Número do Pedido</p>
<p style="color:#722F37;font-size:28px;font-weight:bold;margin:0;">#{{order_number}}</p>
<p style="color:#666;font-size:18px;margin:10px 0 0;">Total: R$ {{order_total}}</p>
</div>
<p style="font-size:16px;color:#666;line-height:1.6;">Você receberá atualizações sobre o status do seu pedido.</p>
</td></tr>
<tr><td style="background:#f9f9f9;padding:30px;text-align:center;">
<p style="color:#999;font-size:12px;margin:0;">{{store_name}} - Massas Artesanais</p>
</td></tr>
</table>
</body>
</html>''',
                'delay_minutes': 0,
            },
            {
                'trigger_type': 'payment_confirmed',
                'name': 'Pagamento Confirmado',
                'subject': 'Pagamento confirmado - Pedido #{{order_number}} ✅',
                'html_content': '''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#fff;">
<tr><td style="background:linear-gradient(135deg,#16a34a,#22c55e);padding:40px 20px;text-align:center;">
<h1 style="color:#fff;margin:0;font-size:28px;">✅ Pagamento Confirmado!</h1>
</td></tr>
<tr><td style="padding:40px 30px;">
<p style="font-size:18px;color:#333;">Olá, <strong>{{customer_name}}</strong>!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">O pagamento do seu pedido <strong>#{{order_number}}</strong> foi confirmado com sucesso!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Seu pedido está sendo preparado e em breve você receberá mais atualizações.</p>
<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:12px;padding:20px;margin:20px 0;text-align:center;">
<p style="color:#16a34a;font-size:24px;font-weight:bold;margin:0;">R$ {{order_total}}</p>
<p style="color:#16a34a;font-size:14px;margin:5px 0 0;">Pagamento recebido</p>
</div>
</td></tr>
<tr><td style="background:#f9f9f9;padding:30px;text-align:center;">
<p style="color:#999;font-size:12px;margin:0;">{{store_name}} - Massas Artesanais</p>
</td></tr>
</table>
</body>
</html>''',
                'delay_minutes': 0,
            },
            {
                'trigger_type': 'order_shipped',
                'name': 'Pedido Saiu para Entrega',
                'subject': 'Pedido #{{order_number}} saiu para entrega! 🚚',
                'html_content': '''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#fff;">
<tr><td style="background:linear-gradient(135deg,#3b82f6,#60a5fa);padding:40px 20px;text-align:center;">
<h1 style="color:#fff;margin:0;font-size:28px;">🚚 Pedido a Caminho!</h1>
</td></tr>
<tr><td style="padding:40px 30px;">
<p style="font-size:18px;color:#333;">Olá, <strong>{{customer_name}}</strong>!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Seu pedido <strong>#{{order_number}}</strong> saiu para entrega!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Em breve você receberá suas deliciosas massas artesanais. 🍝</p>
<div style="background:#eff6ff;border:1px solid #93c5fd;border-radius:12px;padding:20px;margin:20px 0;text-align:center;">
<p style="color:#3b82f6;font-size:18px;font-weight:bold;margin:0;">Fique atento!</p>
<p style="color:#3b82f6;font-size:14px;margin:5px 0 0;">Nosso entregador está a caminho</p>
</div>
</td></tr>
<tr><td style="background:#f9f9f9;padding:30px;text-align:center;">
<p style="color:#999;font-size:12px;margin:0;">{{store_name}} - Massas Artesanais</p>
</td></tr>
</table>
</body>
</html>''',
                'delay_minutes': 0,
            },
            {
                'trigger_type': 'order_delivered',
                'name': 'Pedido Entregue',
                'subject': 'Pedido #{{order_number}} entregue! Bom apetite! 🎉',
                'html_content': '''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#fff;">
<tr><td style="background:linear-gradient(135deg,#722F37,#8B3A44);padding:40px 20px;text-align:center;">
<h1 style="color:#fff;margin:0;font-size:28px;">🎉 Pedido Entregue!</h1>
</td></tr>
<tr><td style="padding:40px 30px;">
<p style="font-size:18px;color:#333;">Olá, <strong>{{customer_name}}</strong>!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Seu pedido <strong>#{{order_number}}</strong> foi entregue com sucesso!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Esperamos que você aproveite suas massas artesanais. Bom apetite! 🍝</p>
<div style="background:linear-gradient(135deg,#C9A050,#D4AF61);border-radius:12px;padding:20px;margin:20px 0;text-align:center;">
<p style="color:#722F37;font-size:14px;margin:0 0 10px;">Gostou? Na próxima compra use:</p>
<p style="color:#722F37;font-size:24px;font-weight:bold;margin:0;">VOLTEI10</p>
<p style="color:#722F37;font-size:14px;margin:5px 0 0;">e ganhe 10% de desconto!</p>
</div>
</td></tr>
<tr><td style="background:#f9f9f9;padding:30px;text-align:center;">
<p style="color:#999;font-size:12px;margin:0;">Obrigado por escolher a {{store_name}}!</p>
</td></tr>
</table>
</body>
</html>''',
                'delay_minutes': 0,
            },
            {
                'trigger_type': 'cart_abandoned',
                'name': 'Carrinho Abandonado',
                'subject': 'Esqueceu algo no carrinho? 🛒',
                'html_content': '''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#fff;">
<tr><td style="background:linear-gradient(135deg,#722F37,#8B3A44);padding:40px 20px;text-align:center;">
<h1 style="color:#fff;margin:0;font-size:28px;">🛒 Você esqueceu algo!</h1>
</td></tr>
<tr><td style="padding:40px 30px;">
<p style="font-size:18px;color:#333;">Olá, <strong>{{customer_name}}</strong>!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Notamos que você deixou alguns itens no carrinho. Suas massas artesanais estão esperando por você!</p>
<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:12px;padding:20px;margin:20px 0;text-align:center;">
<p style="color:#92400e;font-size:18px;font-weight:bold;margin:0;">Finalize sua compra agora!</p>
<p style="color:#92400e;font-size:14px;margin:5px 0 0;">Seus itens ainda estão disponíveis</p>
</div>
<div style="text-align:center;margin:30px 0;">
<a href="https://pastita.com.br/checkout" style="display:inline-block;background:#722F37;color:#fff;text-decoration:none;padding:16px 40px;border-radius:8px;font-size:16px;font-weight:bold;">Finalizar Pedido →</a>
</div>
</td></tr>
<tr><td style="background:#f9f9f9;padding:30px;text-align:center;">
<p style="color:#999;font-size:12px;margin:0;">{{store_name}} - Massas Artesanais</p>
</td></tr>
</table>
</body>
</html>''',
                'delay_minutes': 30,
            },
            {
                'trigger_type': 'order_cancelled',
                'name': 'Pedido Cancelado',
                'subject': 'Pedido #{{order_number}} cancelado',
                'html_content': '''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#fff;">
<tr><td style="background:#6b7280;padding:40px 20px;text-align:center;">
<h1 style="color:#fff;margin:0;font-size:28px;">Pedido Cancelado</h1>
</td></tr>
<tr><td style="padding:40px 30px;">
<p style="font-size:18px;color:#333;">Olá, <strong>{{customer_name}}</strong>!</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Seu pedido <strong>#{{order_number}}</strong> foi cancelado.</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Se você não solicitou o cancelamento ou tem alguma dúvida, entre em contato conosco.</p>
<p style="font-size:16px;color:#666;line-height:1.6;">Esperamos vê-lo novamente em breve!</p>
<div style="text-align:center;margin:30px 0;">
<a href="https://pastita.com.br/cardapio" style="display:inline-block;background:#722F37;color:#fff;text-decoration:none;padding:16px 40px;border-radius:8px;font-size:16px;font-weight:bold;">Ver Cardápio →</a>
</div>
</td></tr>
<tr><td style="background:#f9f9f9;padding:30px;text-align:center;">
<p style="color:#999;font-size:12px;margin:0;">{{store_name}} - Massas Artesanais</p>
</td></tr>
</table>
</body>
</html>''',
                'delay_minutes': 0,
            },
        ]

        created_count = 0
        updated_count = 0

        for data in automations_data:
            if force:
                EmailAutomation.objects.filter(
                    store=store,
                    trigger_type=data['trigger_type']
                ).delete()

            automation, created = EmailAutomation.objects.get_or_create(
                store=store,
                trigger_type=data['trigger_type'],
                defaults={
                    'name': data['name'],
                    'subject': data['subject'],
                    'html_content': data['html_content'],
                    'delay_minutes': data['delay_minutes'],
                    'is_active': True,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(f'  ✅ Created: {data["trigger_type"]} - {data["name"]}')
            else:
                if force:
                    updated_count += 1
                    self.stdout.write(f'  🔄 Updated: {data["trigger_type"]} - {data["name"]}')
                else:
                    self.stdout.write(f'  ⏭️  Exists: {data["trigger_type"]} - {data["name"]}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Done! Created: {created_count}, Updated: {updated_count}'))
        self.stdout.write(f'Total automations for {store.name}: {EmailAutomation.objects.filter(store=store).count()}')
