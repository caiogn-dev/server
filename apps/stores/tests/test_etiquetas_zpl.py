"""Etiqueta remota: painel manda os dados da etiqueta, backend vira ZPL e enfileira
para o agent da Zebra. A Zebra ZD220 é 203 dpi = 8 pontos por mm.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StorePrintAgent, StorePrintJob, StoreSubscription
from apps.stores.services.etiquetas_zpl import render_etiquetas

User = get_user_model()

VALIDADE = [{'name': 'Salada Caesar', 'manip': '25/09/2026', 'val': '30/09/2026'}]
NUTRI = [{
    'name': 'Bowl de frango', 'servingG': 350, 'householdMeasure': '1 unidade',
    'per100g': {'energy_kcal': 128, 'carbohydrates_g': 28.1, 'total_sugars_g': None,
                'added_sugars_g': 0, 'protein_g': 8.5, 'total_fat_g': 4.2,
                'saturated_fat_g': 1.1, 'trans_fat_g': 0, 'fiber_g': 3.2, 'sodium_mg': 210},
    'perServing': {'energy_kcal': 448, 'carbohydrates_g': 98, 'protein_g': 30,
                   'total_fat_g': 15, 'saturated_fat_g': 3.9, 'trans_fat_g': 0,
                   'fiber_g': 11, 'sodium_mg': 735, 'added_sugars_g': 0, 'total_sugars_g': None},
    'allergens': 'ALÉRGICOS: CONTÉM GLÚTEN.', 'frontOfPack': ['ALTO EM SÓDIO'],
    'publicUrl': 'https://backend.pastita.com.br/api/v1/nutrition/public/abc/',
}]
CFG_VALIDADE = {'cols': 3, 'labelW': 33, 'labelH': 22, 'gap': 2, 'paperW': 105,
                'offsetX': 0, 'offsetY': 0}


class RenderTests(APITestCase):
    def test_validade_uma_por_coluna_na_mesma_linha(self):
        tres = [dict(VALIDADE[0], name=f'Prato {i}') for i in range(3)]
        zpl = render_etiquetas('validade', tres, CFG_VALIDADE)
        self.assertEqual(zpl.count('^XA'), 1)          # 3 colunas = 1 linha = 1 rótulo físico
        self.assertIn('^PW840', zpl)                    # 105 mm × 8
        self.assertIn('^LL176', zpl)                    # 22 mm × 8
        self.assertIn('Prato 0', zpl); self.assertIn('Prato 2', zpl)
        # margem centralizada = (105 − 103)/2 = 1 mm; 2ª coluna em (1 + 35) mm + 1,6 mm de respiro = 37,6 mm × 8 = 301 pontos
        self.assertIn('^FO301,', zpl)
        self.assertIn('Val.: 30/09/2026', zpl)

    def test_validade_quatro_etiquetas_em_tres_colunas_dao_duas_linhas(self):
        quatro = [dict(VALIDADE[0], name=f'Prato {i}') for i in range(4)]
        zpl = render_etiquetas('validade', quatro, CFG_VALIDADE)
        self.assertEqual(zpl.count('^XA'), 2)
        self.assertEqual(zpl.count('^XZ'), 2)

    def test_nutricao_100x80_tem_tabela_qr_e_selo(self):
        zpl = render_etiquetas('nutricao', NUTRI, {})
        self.assertIn('^PW800', zpl); self.assertIn('^LL640', zpl)
        self.assertIn('INFORMAÇÃO NUTRICIONAL', zpl)
        self.assertIn('Sódio (mg)', zpl)
        self.assertIn('^BQN', zpl)
        self.assertIn('QA,https://backend.pastita.com.br/api/v1/nutrition/public/abc/', zpl)
        self.assertIn('ALTO EM SÓDIO', zpl)
        self.assertIn('CONTÉM GLÚTEN', zpl)
        self.assertIn('^CI28', zpl)                     # UTF-8: acentos saem certos

    def test_nutricao_usa_coluna_da_porcao_ja_arredondada_e_vd(self):
        zpl = render_etiquetas('nutricao', NUTRI, {})
        # sódio: 735 mg na porção / 2000 = 37 %VD
        self.assertRegex(zpl, r'Sódio \(mg\).*?210.*?735.*?37')
        # açúcares totais sem valor → travessão, nunca "0"
        self.assertRegex(zpl, r'Açúcares totais \(g\)[^\n]*?-')

    def test_nutricao_qr_30x22(self):
        zpl = render_etiquetas('nutricao-qr', NUTRI, {})
        self.assertIn('^PW240', zpl); self.assertIn('^LL176', zpl)
        self.assertIn('^BQN', zpl); self.assertIn('Bowl de frango', zpl)

    def test_caracteres_de_controle_do_zpl_sao_neutralizados(self):
        zpl = render_etiquetas('validade', [dict(VALIDADE[0], name='Prato ^XZ ~JA')], CFG_VALIDADE)
        self.assertEqual(zpl.count('^XZ'), 1)
        self.assertNotIn('~JA', zpl)

    def test_modelo_desconhecido(self):
        with self.assertRaises(ValueError):
            render_etiquetas('comanda', VALIDADE, {})


PRODUTO = [{'name': 'Bowl de frango', 'description': 'Frango, arroz integral, brócolis', 'price': 'R$ 29,90', 'barcode': '2010000000015'}]
CFG_PRODUTO = {'width': 100, 'height': 80, 'paperW': 100, 'rotate': False, 'offsetX': 0, 'offsetY': 0,
               'border': 'solid', 'showPrice': True, 'showDesc': True}


class RenderProdutoTests(APITestCase):
    def test_produto_100x80_com_ean13_preco_e_borda(self):
        zpl = render_etiquetas('produto', PRODUTO, CFG_PRODUTO)
        self.assertIn('^PW800', zpl); self.assertIn('^LL640', zpl)
        self.assertIn('Bowl de frango', zpl)
        self.assertIn('R$ 29,90', zpl)
        self.assertIn('^BEN', zpl)                     # EAN-13 nativo
        self.assertIn('^FD2010000000015^FS', zpl)
        self.assertIn('^GB', zpl)                      # borda
        self.assertIn('Frango, arroz integral', zpl)

    def test_codigo_que_nao_e_ean13_sai_em_code128(self):
        zpl = render_etiquetas('produto', [dict(PRODUTO[0], barcode='ABC-77')], CFG_PRODUTO)
        self.assertIn('^BCN', zpl); self.assertNotIn('^BEN', zpl)

    def test_sem_preco_e_sem_descricao_quando_desligados(self):
        zpl = render_etiquetas('produto', PRODUTO, dict(CFG_PRODUTO, showPrice=False, showDesc=False, border='none'))
        self.assertNotIn('R$ 29,90', zpl); self.assertNotIn('Frango, arroz', zpl); self.assertNotIn('^GB', zpl)

    def test_girar_90_troca_largura_por_altura(self):
        zpl = render_etiquetas('produto', PRODUTO, dict(CFG_PRODUTO, rotate=True, width=100, height=50, paperW=100))
        self.assertIn('^PW400', zpl); self.assertIn('^LL800', zpl); self.assertIn('^FWR', zpl)

    def test_sem_codigo_nao_manda_barcode(self):
        zpl = render_etiquetas('produto', [dict(PRODUTO[0], barcode='')], CFG_PRODUTO)
        self.assertNotIn('^BEN', zpl); self.assertNotIn('^BCN', zpl)


class EndpointTests(APITestCase):
    URL = '/api/v1/stores/print-jobs/etiquetas/'

    def setUp(self):
        self.owner = User.objects.create_user(username='dono-zpl', email='dono-zpl@t.local', password='x')
        self.outro = User.objects.create_user(username='outro-zpl', email='outro-zpl@t.local', password='x')
        self.store = Store.objects.create(name='Loja Z', slug='loja-z', owner=self.owner, status='active')
        self.loja_alheia = Store.objects.create(name='Alheia', slug='alheia-z', owner=self.outro, status='active')
        _, p, h = StorePrintAgent.generate_api_key()
        self.zebra = StorePrintAgent.objects.create(
            store=self.store, name='pc desktop', slug='pc-desktop-z', station='kitchen',
            printer_name='ZDesigner ZD220-203dpi ZPL', imprime=['etiquetas'], api_key_prefix=p, api_key_hash=h)
        _, p2, h2 = StorePrintAgent.generate_api_key()
        self.agent_alheio = StorePrintAgent.objects.create(
            store=self.loja_alheia, name='x', slug='x-z', api_key_prefix=p2, api_key_hash=h2)
        self.client.force_authenticate(self.owner)

    def _post(self, **extra):
        body = {'store': str(self.store.id), 'agent': str(self.zebra.id),
                'modelo': 'validade', 'etiquetas': VALIDADE, 'config': CFG_VALIDADE}
        body.update(extra)
        return self.client.post(self.URL, body, format='json')

    def test_cria_job_zpl_apontado_para_o_agent(self):
        r = self._post()
        self.assertEqual(r.status_code, 201, r.content)
        job = StorePrintJob.objects.get(id=r.data['job']['id'])
        self.assertEqual(job.template, 'etiqueta_zpl')
        self.assertEqual(job.target_agent_id, self.zebra.id)
        self.assertEqual(job.station, self.zebra.station)
        self.assertEqual(job.source, 'etiqueta')
        self.assertIn('^XA', job.payload['zpl'])
        self.assertEqual(job.payload['modelo'], 'validade')
        self.assertEqual(job.payload['quantidade'], 1)
        self.assertIn('validade', job.title)

    def test_agent_de_outra_loja_e_recusado(self):
        r = self._post(agent=str(self.agent_alheio.id))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(StorePrintJob.objects.count(), 0)

    def test_loja_alheia_e_recusada(self):
        r = self._post(store=str(self.loja_alheia.id), agent=str(self.agent_alheio.id))
        self.assertIn(r.status_code, (403, 404))
        self.assertEqual(StorePrintJob.objects.count(), 0)

    def test_nutricao_exige_o_adicional(self):
        StoreSubscription.objects.create(store=self.store, plan='pro', status='active')
        r = self._post(modelo='nutricao', etiquetas=NUTRI, config={})
        self.assertEqual(r.status_code, 402)
        StoreSubscription.objects.filter(store=self.store).update(adicionais={'etiqueta_anvisa': {}})
        r = self._post(modelo='nutricao', etiquetas=NUTRI, config={})
        self.assertEqual(r.status_code, 201, r.content)

    def test_produto_e_modelo_valido_no_endpoint(self):
        r = self._post(modelo='produto', etiquetas=PRODUTO, config=CFG_PRODUTO)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn('^BEN', StorePrintJob.objects.get().payload['zpl'])

    def test_sem_etiquetas_e_400(self):
        r = self._post(etiquetas=[])
        self.assertEqual(r.status_code, 400)

    def test_agent_pega_o_job_pela_api_dele(self):
        self._post()
        raw, p, h = StorePrintAgent.generate_api_key()
        self.zebra.api_key_prefix, self.zebra.api_key_hash = p, h
        self.zebra.save()
        r = self.client.post('/api/v1/stores/print/agent/claim-next/', {}, format='json',
                             HTTP_X_PRINT_AGENT_KEY=raw)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['job']['template'], 'etiqueta_zpl')
        self.assertIn('^XA', r.data['job']['payload']['zpl'])
