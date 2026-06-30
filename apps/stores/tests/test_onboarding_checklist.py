from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.stores.models import Store
from apps.stores.models.delivery import StoreDeliveryZone
from apps.stores.services.onboarding_checklist import build_checklist

User = get_user_model()


def _store(**kw):
    owner = User.objects.create_user(
        username=f"o-{kw.get('slug','x')}", email=f"{kw.get('slug','x')}@t.local", password='x')
    return Store.objects.create(name=kw.get('slug', 'L'), slug=kw.get('slug', 'l'), owner=owner)


class BuildChecklistTest(TestCase):
    def test_loja_vazia_so_account(self):
        c = build_checklist(_store(slug='vazia'))
        self.assertEqual(c['total'], 6)
        self.assertEqual(c['completed'], 1)  # só 'account'
        self.assertFalse(c['all_done'])
        done = {s['key']: s['done'] for s in c['steps']}
        self.assertTrue(done['account'])
        self.assertFalse(done['logo'])
        self.assertFalse(done['product'])
        self.assertFalse(done['delivery'])
        self.assertFalse(done['hours'])
        self.assertFalse(done['whatsapp'])

    def test_ordem_e_labels_presentes(self):
        c = build_checklist(_store(slug='ord'))
        self.assertEqual([s['key'] for s in c['steps']],
                         ['account', 'logo', 'product', 'delivery', 'hours', 'whatsapp'])
        self.assertTrue(all(s['label'] for s in c['steps']))

    def test_logo_url_externa_conta(self):
        s = _store(slug='logo')
        s.logo_url = 'https://x/y.png'; s.save(update_fields=['logo_url'])
        done = {x['key']: x['done'] for x in build_checklist(s)['steps']}
        self.assertTrue(done['logo'])

    def test_horario_e_whatsapp(self):
        s = _store(slug='hw')
        s.operating_hours = {'monday': {'open': '09:00', 'close': '18:00'}}
        s.whatsapp_number = '5563999999999'
        s.save(update_fields=['operating_hours', 'whatsapp_number'])
        done = {x['key']: x['done'] for x in build_checklist(s)['steps']}
        self.assertTrue(done['hours'])
        self.assertTrue(done['whatsapp'])

    def test_zona_de_entrega_conta_como_delivery(self):
        s = _store(slug='deliv')
        StoreDeliveryZone.objects.create(store=s, name='Centro', delivery_fee=5)
        done = {x['key']: x['done'] for x in build_checklist(s)['steps']}
        self.assertTrue(done['delivery'])

    def test_all_done(self):
        s = _store(slug='full')
        s.logo_url = 'https://x/y.png'
        s.operating_hours = {'monday': {'open': '09:00', 'close': '18:00'}}
        s.whatsapp_number = '556399'
        s.save()
        from apps.stores.models.product import StoreProduct  # noqa
        # cria 1 produto mínimo; slug é SlugField sem default, então setamos explicitamente
        StoreProduct.objects.create(store=s, name='X', slug='x', price=10)
        StoreDeliveryZone.objects.create(store=s, name='Centro', delivery_fee=5)
        c = build_checklist(s)
        self.assertTrue(c['all_done'])
        self.assertEqual(c['completed'], 6)
