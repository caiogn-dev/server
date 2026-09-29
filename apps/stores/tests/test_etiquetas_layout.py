"""Etiqueta desenhada (layout em mm → bitmap → ^GFA).

Por que bitmap: a Zebra e a Elgin (emulação ZPL) desenham as fontes ^A0 de
jeitos diferentes, e "Manip.:" que cabe numa cai fora da outra. Um bitmap sai
igual nas duas — e a prévia do painel É o bitmap que vai imprimir.
Calibração (deslocamento em mm) vive no agent, não no layout: é a impressora
que está torta, não o desenho.
"""
import base64
import math

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StorePrintAgent, StorePrintJob
from apps.stores.services import etiquetas_layout as motor

User = get_user_model()

VALIDADE = {'name': 'Salada Caesar', 'manip': '25/09/2026', 'val': '30/09/2026'}


class RenderBitmapTests(APITestCase):
    def test_layout_padrao_de_validade_replica_o_rolo_de_3(self):
        lay = motor.layout_padrao('validade')
        self.assertEqual(lay['papel']['colunas'], 3)
        self.assertEqual(lay['etiqueta']['largura'], 33)
        self.assertTrue(any(e['tipo'] == 'texto' and '{val}' in e['texto'] for e in lay['elementos']))

    def test_zpl_de_uma_linha_fisica_tem_um_bitmap_do_papel_inteiro(self):
        lay = motor.layout_padrao('validade')            # 3 × 33 + 2 × 2 = 103 mm em papel de 107
        tres = [dict(VALIDADE, name=f'Prato {i}') for i in range(3)]
        zpl = motor.render_zpl(lay, tres)
        self.assertEqual(zpl.count('^XA'), 1)
        self.assertIn('^PW856', zpl); self.assertIn('^LL176', zpl)
        bpr = math.ceil(856 / 8); total = bpr * 176
        self.assertIn(f'^GFA,{total},{total},{bpr},', zpl)
        self.assertEqual(zpl.count('^GFA'), 1)          # o papel inteiro é UM desenho

    def test_quatro_etiquetas_em_tres_colunas_dao_duas_linhas(self):
        lay = motor.layout_padrao('validade')
        zpl = motor.render_zpl(lay, [dict(VALIDADE) for _ in range(4)])
        self.assertEqual(zpl.count('^XA'), 2); self.assertEqual(zpl.count('^GFA'), 2)

    def test_calibracao_vira_ls_e_lt_da_impressora_nao_mexe_no_desenho(self):
        lay = motor.layout_padrao('validade')
        zpl = motor.render_zpl(lay, [VALIDADE], calibracao={'desloc_x': -2, 'desloc_y': 1.5, 'escuro': 20})
        self.assertIn('^LS-16', zpl); self.assertIn('^LT12', zpl); self.assertIn('^MD20', zpl)
        sem = motor.render_zpl(lay, [VALIDADE])
        self.assertIn('^LS0', sem); self.assertIn('^LT0', sem)

    def test_rolo_com_vao_manda_modo_gap_e_continuo_usa_o_passo_como_altura(self):
        """Manual da L42 PRO: se a calibração falha a impressora cai em 'Contínuo' e
        avança só ^LL por etiqueta — com passo real de 25 mm, desliza 3 mm por linha.
        ^MNY força o sensor de vão; em contínuo, ^LL precisa ser o passo, não a altura."""
        lay = motor.layout_padrao('validade')
        zpl = motor.render_zpl(lay, [VALIDADE])
        self.assertIn('^MNY', zpl); self.assertIn('^LL176', zpl)
        lay['papel']['modo_midia'] = 'continuo'; lay['papel']['passo'] = 25
        zpl = motor.render_zpl(lay, [VALIDADE])
        self.assertIn('^MNN', zpl); self.assertIn('^LL200', zpl)
        lay['papel']['modo_midia'] = 'auto'
        zpl = motor.render_zpl(lay, [VALIDADE])
        self.assertNotIn('^MN', zpl)
        with self.assertRaises(motor.LayoutInvalido):
            motor.validar_layout(dict(lay, papel=dict(lay['papel'], modo_midia='foguete')))

    def test_fontes_e_ajuste_em_uma_linha(self):
        """`fonte` escolhe a família (Liberation: sans, estreita, serif, mono) e
        `ajuste: 'encolher'` mantém o texto em UMA linha, diminuindo a letra até caber."""
        lay = motor.layout_padrao('validade')
        nome = lay['elementos'][0]
        nome.update({'ajuste': 'encolher', 'w': 20, 'h': 4, 'tamanho': 3, 'linhas': 1})
        et = {'name': 'Salada Caesar com frango grelhado e molho', 'manip': '1', 'val': '2'}
        img = motor.render_bitmap(lay, [et])
        # tinta só dentro da caixa do nome (x 2+1.6 .. +20 mm; y 1.4 .. 5.4 mm)
        self.assertTrue(motor._tem_tinta(img, 3.6, 1.4, 23.6, 5.4))
        self.assertFalse(motor._tem_tinta(img, 23.8, 1.4, 35, 5.6))       # não passou da largura
        self.assertFalse(motor._tem_tinta(img, 3.6, 5.6, 23.6, 12))       # não desceu para 2ª linha
        # famílias diferentes produzem bitmaps diferentes; desconhecida é recusada
        lay_serif = motor.layout_padrao('validade'); lay_serif['elementos'][0]['fonte'] = 'serif'
        self.assertNotEqual(motor.render_bitmap(lay, [VALIDADE]).tobytes(), motor.render_bitmap(lay_serif, [VALIDADE]).tobytes())
        for fam in motor.FONTES:
            self.assertTrue(motor._fonte(20, False, fam).getname()[0].startswith('Liberation'), fam)
        with self.assertRaises(motor.LayoutInvalido):
            motor.validar_layout(dict(lay, elementos=[dict(nome, fonte='comic')]))
        with self.assertRaises(motor.LayoutInvalido):
            motor.validar_layout(dict(lay, elementos=[dict(nome, ajuste='esticar')]))

    def test_bitmap_tem_tinta_no_nome_e_papel_limpo_no_vao_entre_colunas(self):
        lay = motor.layout_padrao('validade')
        img = motor.render_bitmap(lay, [dict(VALIDADE, name='XXXXXXXX')] * 3)
        self.assertEqual(img.size, (856, 176))
        # nome da 1ª coluna: começa em (margem 2 + 1,6) mm → há preto na faixa de 4..30 mm × 1,4..8 mm
        self.assertTrue(motor._tem_tinta(img, 4, 1.4, 30, 8))
        # vão entre a 1ª e a 2ª coluna: 2+33 = 35 mm até 37 mm → nada
        self.assertFalse(motor._tem_tinta(img, 35.2, 0, 36.8, 22))

    def test_texto_substitui_campos_e_ignora_campo_desconhecido(self):
        self.assertEqual(motor.preencher('Val.: {val} {nada}', VALIDADE), 'Val.: 30/09/2026 ')

    def test_qr_e_barras_saem_nativos_no_lugar_do_layout(self):
        lay = motor.layout_padrao('nutricao-qr')
        et = {'name': 'Bowl', 'publicUrl': 'https://x/abc/'}
        zpl = motor.render_zpl(lay, [et])
        self.assertIn('^BQN,2,', zpl); self.assertIn('^FDQA,https://x/abc/', zpl)
        lay_p = motor.layout_padrao('produto')
        zpl_p = motor.render_zpl(lay_p, [{'name': 'Suco', 'price': 'R$ 9,90', 'barcode': '7891234567895'}])
        self.assertIn('^BEN', zpl_p)
        zpl_c = motor.render_zpl(lay_p, [{'name': 'Suco', 'barcode': 'ABC123'}])
        self.assertIn('^BCN', zpl_c)

    def test_controle_do_zpl_nos_campos_nativos_e_neutralizado(self):
        lay = motor.layout_padrao('nutricao-qr')
        zpl = motor.render_zpl(lay, [{'name': 'x', 'publicUrl': 'https://x/^XZ~JA'}])
        self.assertEqual(zpl.count('^XZ'), 1)

    def test_layout_invalido_e_recusado(self):
        with self.assertRaises(motor.LayoutInvalido):
            motor.validar_layout({'etiqueta': {'largura': 0, 'altura': 22}, 'papel': {}, 'elementos': []})
        with self.assertRaises(motor.LayoutInvalido):
            motor.validar_layout({'etiqueta': {'largura': 33, 'altura': 22}, 'papel': {'colunas': 1},
                                  'elementos': [{'tipo': 'foguete', 'x': 0, 'y': 0, 'w': 1, 'h': 1}]})

    def test_grade_de_calibracao_desenha_uma_moldura_por_coluna(self):
        lay = motor.layout_padrao('validade')
        zpl = motor.grade_de_calibracao(lay)
        self.assertEqual(zpl.count('^XA'), 1); self.assertIn('^GFA', zpl)
        img = motor.render_bitmap(lay, [], elementos=motor.elementos_da_grade(lay))
        # moldura da 1ª etiqueta: borda esquerda em x = 2 mm (margem centralizada)
        self.assertTrue(motor._tem_tinta(img, 1.8, 5, 2.4, 6))
        # moldura da 3ª: borda direita em 2 + 3×33 + 2×2 = 105 mm
        self.assertTrue(motor._tem_tinta(img, 104.6, 5, 105.2, 6))

    def test_preview_png(self):
        png = motor.preview_png(motor.layout_padrao('validade'), [VALIDADE])
        self.assertTrue(png.startswith(b'\x89PNG'))


class ApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dona-l', email='dona-l@t.local', password='x')
        self.outro = User.objects.create_user(username='outro-l', email='outro-l@t.local', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja-l', owner=self.owner, status='active')
        _, p, h = StorePrintAgent.generate_api_key()
        self.agent = StorePrintAgent.objects.create(
            store=self.store, name='pc desktop', slug='pc-desktop-l', station='kitchen',
            printer_name='ELGIN L42PRO FULL', imprime=['etiquetas'], api_key_prefix=p, api_key_hash=h,
            metadata={'alerta': {'codigo': 'offline'}},
        )
        self.client.force_authenticate(self.owner)

    def test_layouts_padrao_e_salvo(self):
        r = self.client.get('/api/v1/stores/print-jobs/etiquetas/layouts/', {'store': str(self.store.id)})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['validade']['padrao'])
        lay = r.data['validade']['layout']
        lay['etiqueta']['largura'] = 30
        r = self.client.put('/api/v1/stores/print-jobs/etiquetas/layouts/',
                            {'store': str(self.store.id), 'modelo': 'validade', 'layout': lay}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.metadata['etiquetas_layouts']['validade']['etiqueta']['largura'], 30)
        r = self.client.get('/api/v1/stores/print-jobs/etiquetas/layouts/', {'store': str(self.store.id)})
        self.assertFalse(r.data['validade']['padrao'])
        # layout: null = volta ao padrão
        r = self.client.put('/api/v1/stores/print-jobs/etiquetas/layouts/',
                            {'store': str(self.store.id), 'modelo': 'validade', 'layout': None}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['padrao'])

    def test_layout_invalido_da_400_e_loja_alheia_404(self):
        r = self.client.put('/api/v1/stores/print-jobs/etiquetas/layouts/',
                            {'store': str(self.store.id), 'modelo': 'validade',
                             'layout': {'etiqueta': {'largura': 0}, 'papel': {}, 'elementos': []}}, format='json')
        self.assertEqual(r.status_code, 400)
        self.client.force_authenticate(self.outro)
        r = self.client.get('/api/v1/stores/print-jobs/etiquetas/layouts/', {'store': str(self.store.id)})
        self.assertEqual(r.status_code, 404)

    def test_preview_devolve_png(self):
        r = self.client.post('/api/v1/stores/print-jobs/etiquetas/preview/', {
            'store': str(self.store.id), 'modelo': 'validade', 'etiquetas': [VALIDADE],
        }, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(base64.b64decode(r.data['png']).startswith(b'\x89PNG'))
        self.assertEqual(r.data['largura_mm'], 107); self.assertEqual(r.data['altura_mm'], 22)

    def test_calibracao_do_agent_preserva_o_resto_do_metadata(self):
        r = self.client.post(f'/api/v1/stores/print-agents/{self.agent.id}/calibracao/',
                             {'desloc_x': -2, 'desloc_y': 1, 'escuro': 15}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.metadata['calibracao'], {'desloc_x': -2.0, 'desloc_y': 1.0, 'escuro': 15})
        self.assertEqual(self.agent.metadata['alerta']['codigo'], 'offline')
        r = self.client.post(f'/api/v1/stores/print-agents/{self.agent.id}/calibracao/',
                             {'desloc_x': 99}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_imprimir_com_motor_bitmap_usa_layout_salvo_e_calibracao_do_agent(self):
        self.agent.metadata['calibracao'] = {'desloc_x': -1, 'desloc_y': 0}
        self.agent.save()
        r = self.client.post('/api/v1/stores/print-jobs/etiquetas/', {
            'store': str(self.store.id), 'agent': str(self.agent.id), 'modelo': 'validade',
            'etiquetas': [VALIDADE], 'motor': 'bitmap',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        job = StorePrintJob.objects.get()
        self.assertIn('^GFA', job.payload['zpl']); self.assertIn('^LS-8', job.payload['zpl'])
        self.assertEqual(job.payload['motor'], 'bitmap')

    def test_sem_motor_continua_no_zpl_antigo(self):
        r = self.client.post('/api/v1/stores/print-jobs/etiquetas/', {
            'store': str(self.store.id), 'agent': str(self.agent.id), 'modelo': 'validade',
            'etiquetas': [VALIDADE], 'config': {'cols': 3, 'labelW': 33, 'labelH': 22, 'gap': 2, 'paperW': 107},
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertNotIn('^GFA', StorePrintJob.objects.get().payload['zpl'])

    def test_grade_de_calibracao_vira_job_para_o_agent(self):
        r = self.client.post('/api/v1/stores/print-jobs/etiquetas/calibracao/', {
            'store': str(self.store.id), 'agent': str(self.agent.id), 'modelo': 'validade',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        job = StorePrintJob.objects.get()
        self.assertEqual(job.target_agent_id, self.agent.id)
        self.assertIn('^GFA', job.payload['zpl']); self.assertEqual(job.payload['modelo'], 'calibracao')
