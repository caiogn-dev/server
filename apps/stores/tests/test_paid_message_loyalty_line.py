from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreLoyaltyAccount

User = get_user_model()


class PaidMessageLoyaltyLineTest(TestCase):
    def test_linha_de_fidelidade_para_cliente_com_saldo(self):
        owner = User.objects.create_user(username='dono5', password='x')
        cli = User.objects.create_user(username='cli5', password='x')
        store = Store.objects.create(name='L', slug='loja-pm', owner=owner, status='active')
        acc, _ = StoreLoyaltyAccount.objects.get_or_create(store=store, user=cli)
        acc.qualified_count = 7
        acc.save(update_fields=['qualified_count'])
        from apps.stores.models.order import build_loyalty_status_line
        line = build_loyalty_status_line(store, cli)
        assert '7/10' in line and 'faltam 3' in line

    def test_linha_com_premio_disponivel(self):
        owner = User.objects.create_user(username='dono6', password='x')
        cli = User.objects.create_user(username='cli6', password='x')
        store = Store.objects.create(name='L', slug='loja-pm2', owner=owner, status='active')
        StoreLoyaltyAccount.objects.create(store=store, user=cli, qualified_count=10, redeemed_count=0)
        from apps.stores.models.order import build_loyalty_status_line
        assert 'grátis' in build_loyalty_status_line(store, cli)
