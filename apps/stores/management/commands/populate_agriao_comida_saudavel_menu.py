"""
Management command para popular a loja Agrião Comida Saudável.

Fonte: CARDAPIOATUALIZADO2.pdf (cardápio impresso de prefirodelivery.com/agriaocomidasaudavel,
exportado em 10/08/2026) cruzado com o catálogo público da loja para obter as fotos
em resolução original.

Escopo desta carga: apenas os produtos DISPONÍVEIS das 4 linhas pedidas pelo dono
(Linha Fit, Linha Bistrô, Caldos Fit e Sobremesas Artelatto). Os itens marcados
"(indisponível)" no PDF e as demais categorias (Combos, Saladas, Low Carb, Porções,
Lanches, Pastita, dia-a-dia) ficam de fora desta carga.

As fotos ficam em MEDIA_ROOT/stores/products/agriao-comida-saudavel/ e são
otimizadas para WebP pelo ImageOptimizer — a loja não depende do S3 do fornecedor.

Usage:
    python manage.py populate_agriao_comida_saudavel_menu
    python manage.py populate_agriao_comida_saudavel_menu --dry-run
"""
import logging
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.db import transaction

from apps.stores.models import Store, StoreCategory, StoreProduct
from apps.stores.utils.image_optimizer import ImageOptimizer

logger = logging.getLogger(__name__)
User = get_user_model()

STORE_SLUG = 'agriao-comida-saudavel'
OWNER_EMAIL = 'agriaosaudavel.oficial@gmail.com'
IMG_PATH = 'stores/products/agriao-comida-saudavel'
LOGO_FILE = 'logo-agriao.webp'

# Domingo fechado; sábado meio período. Conforme rodapé do cardápio.
OPERATING_HOURS = {
    "monday": {"open": "08:30", "close": "17:00"},
    "tuesday": {"open": "08:30", "close": "17:00"},
    "wednesday": {"open": "08:30", "close": "17:00"},
    "thursday": {"open": "08:30", "close": "17:00"},
    "friday": {"open": "08:30", "close": "17:00"},
    "saturday": {"open": "08:00", "close": "11:30"},
    "sunday": {"open": "00:00", "close": "00:00"},
}

CATEGORIES = [
    {'slug': 'linha-fit', 'name': 'Linha Fit', 'description': 'Refeições congeladas equilibradas para o dia a dia, prontas em minutos.', 'sort_order': 1},
    {'slug': 'linha-bistro', 'name': 'Linha Bistrô', 'description': 'Pratos elaborados de 440g, com preparo e ingredientes de restaurante.', 'sort_order': 2},
    {'slug': 'caldos-fit', 'name': 'Caldos Fit', 'description': 'Caldos encorpados e leves, ideais para o jantar.', 'sort_order': 3},
    {'slug': 'sobremesas-artelatto', 'name': 'Sobremesas Artelatto', 'description': 'Sobremesas geladas artesanais para fechar a refeição.', 'sort_order': 4},
]

PRODUCTS = [
    {'sku': 'AGR-FIT-01', 'category_slug': 'linha-fit', 'name': 'Almôndega premium ao molho de tomate, arroz branco e feijão carioca', 'price': Decimal('24.00'), 'featured': True, 'sort_order': 1,
     'short_description': 'Almôndegas artesanais ao molho pomodoro fresco, servidas com arroz, feijão carioca acompanhada com cenoura, abobrinha, batata-doce (legumes…',
     'description': 'Almôndegas artesanais ao molho pomodoro fresco, servidas com arroz, feijão carioca acompanhada com cenoura, abobrinha, batata-doce (legumes salteados). Porção: 100g arroz 120g almôndega 70g de feijão 50~70g de legumes salteados Ingredientes: Arroz, feijão carioca, almôndega, alho, sal, páprica defumada.',
     'image': 'almondega-premium-ao-molho-de-tomate-arroz-branco-e-feijao-carioca.png',
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-02', 'category_slug': 'linha-fit', 'name': 'Assadinho de panela com arroz, feijão preto e couve.', 'price': Decimal('24.00'), 'featured': True, 'sort_order': 2,
     'short_description': 'Delicioso prato brasileiro, assadinho de panela, arroz branco, feijão preto e couve refogada com alho.',
     'description': 'Delicioso prato brasileiro, assadinho de panela, arroz branco, feijão preto e couve refogada com alho. Uma opção perfeita para sua semana, prático e saboroso para o seu dia-a-dia. Porção: 120g de carne 130g de arroz 40g de couve 40g de feijão preto',
     'image': 'assadinho-de-panela-com-arroz-feijao-preto-e-couve.webp',
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-03', 'category_slug': 'linha-fit', 'name': 'Bobó de Frango e arroz', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 3,
     'short_description': 'Delicioso bobó de frango com arroz e cenoura palito! Perfeito para uma refeição prática e saborosa para seu dia-a-dia!',
     'description': 'Delicioso bobó de frango com arroz e cenoura palito! Perfeito para uma refeição prática e saborosa para seu dia-a-dia! Porção: 180g de Bobó de Frango 100g de arroz 40g cenoura palito',
     'image': 'bobo-de-frango-e-arroz.webp',
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-04', 'category_slug': 'linha-fit', 'name': 'Coxa e sobre coxa grelhada ao molho 3 queijo com legumes', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 4,
     'short_description': '',
     'description': 'Porção: 120g de sobrecoxa desossada, 80g de legumes salteados 110g de arroz branco, 40g de molho de 3 Queijos Ingredientes: Sobrecoxa desossada, arroz branco, cenoura, couve, cebola, pimenta-de-cheiro, cheiro-verde, alho-poró, alecrim, sal, leite desnatado, creme de leite, manteiga, amido de milho, mix de grãos com sementes e banha suína.',
     'image': 'coxa-e-sobre-coxa-grelhada-ao-molho-3-queijo-com-legumes.webp',
     'tags': ['linha-fit']},
    {'sku': 'AGR-FIT-05', 'category_slug': 'linha-fit', 'name': 'Coxa e sobrecoxa, arroz branco, feijão carioca e legumes salteados', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 5,
     'short_description': 'Deliciosa e suculenta coxa e sobrecoxa assada, acompanhada de arroz branco, feijão carioca e legumes salteados.',
     'description': 'Deliciosa e suculenta coxa e sobrecoxa assada, acompanhada de arroz branco, feijão carioca e legumes salteados. A opção perfeita para o seu dia-a-dia. Praticidade e sabor para sua semana! Porção: 120g de arroz 100g de coxa e sobrecoxa 1 concha de feijão 30~50g de legumes salteados',
     'image': 'coxa-e-sobrecoxa-arroz-branco-feijao-carioca-e-legumes-salteados.png',
     'tags': ['linha-fit']},
    {'sku': 'AGR-FIT-06', 'category_slug': 'linha-fit', 'name': 'Escondidinho de Patinho com purê de Banana-da-Terra', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 6,
     'short_description': 'Delicioso e saboroso escondidinho de patinho com purê de banana-da-terra.',
     'description': 'Delicioso e saboroso escondidinho de patinho com purê de banana-da-terra. Porção: 120g de carne (patinho moído), 160g de purê de banana da terra, 20g de queijo mussarela',
     'image': 'escondidinho-de-patinho-com-pure-de-banana-da-terra.webp',
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-07', 'category_slug': 'linha-fit', 'name': 'Escondidinho de frango com purê de banana-da-terra', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 7,
     'short_description': 'Purê leve e cremoso de banana-da-terra, recheado com frango desfiado ao tempero caseiro e finalizado com ervas frescas.',
     'description': 'Purê leve e cremoso de banana-da-terra, recheado com frango desfiado ao tempero caseiro e finalizado com ervas frescas. Uma refeição nutritiva, saborosa e prática — basta aquecer no micro-ondas e está pronto para servir! Peso líquido: 300 g Ingredientes: 120 g frango desfiado, 160 g purê de banana-da-terra, 20g de muçarela zero lactose, temperos frescos',
     'image': 'escondidinho-de-frango-com-pure-de-banana-da-terra.webp',
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-08', 'category_slug': 'linha-fit', 'name': 'Escondidinho de frango com purê de batata', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 8,
     'short_description': 'Delicioso escondidinho de frango com purê de batata, perfeito para praticidade e sabor na sua semana.',
     'description': 'Delicioso escondidinho de frango com purê de batata, perfeito para praticidade e sabor na sua semana. Uma opção perfeita para o seu dia-a-dia! Porção: 160g purê de purê de batata inglesa.120g frango desfiado.20g de mussarela zero lactose',
     'image': 'escondidinho-de-frango-com-pure-de-batata.webp',
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-09', 'category_slug': 'linha-fit', 'name': 'Escondidinho de frango e purê de mandioca', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 9,
     'short_description': 'Delicioso escondidinho de frango com purê de mandioca cremoso. Perfeito para sua semana e praticidade no dia-a-dia.',
     'description': 'Delicioso escondidinho de frango com purê de mandioca cremoso. Perfeito para sua semana e praticidade no dia-a-dia. Porção: 160g Purê de mandioca 130g Frango desfiado',
     'image': 'escondidinho-de-frango-e-pure-de-mandioca.webp',
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-10', 'category_slug': 'linha-fit', 'name': 'Escondidinho de patinho com purê de mandioca', 'price': Decimal('24.00'), 'featured': False, 'sort_order': 10,
     'short_description': 'Delicioso escondidinho de patinho com purê de mandioca cremoso. Perfeito para sua semana e praticidade no dia-a-dia.',
     'description': 'Delicioso escondidinho de patinho com purê de mandioca cremoso. Perfeito para sua semana e praticidade no dia-a-dia. Porção: 160g Purê de mandioca;130g patinho moído.',
     'image': 'escondidinho-de-patinho-com-pure-de-mandioca.webp',
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-11', 'category_slug': 'linha-fit', 'name': 'Escondidinho de patinho e purê de batata.', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 11,
     'short_description': 'Delicioso escondidinho de patinho moído com purê de batata inglesa, perfeito para almoços práticos e com muito sabor!',
     'description': 'Delicioso escondidinho de patinho moído com purê de batata inglesa, perfeito para almoços práticos e com muito sabor! Porção: 120g de patinho moído 160g purê de batata 20g de mussarela zero lactose Ingredientes: patinho moído, colorau, açafrão, sal, pimentão, alho, banha suína, pimenta de cheiro, cheiro-verde, chimichurri, tomate cereja, batata, creme de cebola, creme de leite ZERO LACTOSE, leite ZERO LACTOSE',
     'image': 'escondidinho-de-patinho-e-pure-de-batata.webp',
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-12', 'category_slug': 'linha-fit', 'name': 'Estrogonofe de frango com arroz branco e brócolis.', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 12,
     'short_description': 'Clássico estrogonofe de frango, cremoso e suave, servido com arroz branco soltinho e brócolis levemente al dente.',
     'description': 'Clássico estrogonofe de frango, cremoso e suave, servido com arroz branco soltinho e brócolis levemente al dente. Uma releitura saudável do prato queridinho dos brasileiros. Cremoso na medida certa. Porção: 160g de estrogonofe de frango 130g de arroz branco 30g de brócolis',
     'image': 'estrogonofe-de-frango-com-arroz-branco-e-brocolis.png',
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-13', 'category_slug': 'linha-fit', 'name': 'Filé de frango grelhado com arroz branco e creme de milho', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 13,
     'short_description': 'Filé de frango grelhado, macio e bem temperado, acompanhado de arroz branco soltinho e creme de milho aveludado.',
     'description': 'Filé de frango grelhado, macio e bem temperado, acompanhado de arroz branco soltinho e creme de milho aveludado. Uma refeição leve, cremosa e perfeita para o dia a dia. Porção total: 340 g 130 g de filé de frango grelhado 130 g de arroz branco 80 g de creme de milho',
     'image': 'file-de-frango-grelhado-com-arroz-branco-e-creme-de-milho.png',
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-14', 'category_slug': 'linha-fit', 'name': 'Frango desfiado com creme de milho e arroz branco', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 14,
     'short_description': 'FICHA TÉCNICA: 120g de frango desfiado 130g de arroz branco 70~80g de creme de milho (1 concha) finalizado com mix de grãos',
     'description': 'FICHA TÉCNICA: 120g de frango desfiado 130g de arroz branco 70~80g de creme de milho (1 concha) finalizado com mix de grãos',
     'image': 'frango-desfiado-com-creme-de-milho-e-arroz-branco.png',
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-15', 'category_slug': 'linha-fit', 'name': 'Galinhada FIT', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 15,
     'short_description': 'Arroz soltinho com peito de frango em cubos, legumes, queijo ralado, ervas finas e um toque de cúrcuma para dar sabor e cor.',
     'description': 'Arroz soltinho com peito de frango em cubos, legumes, queijo ralado, ervas finas e um toque de cúrcuma para dar sabor e cor. Porção: 300g de galinhada FIT',
     'image': 'galinhada-fit.webp',
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-16', 'category_slug': 'linha-fit', 'name': 'Parmegiana de frango com arroz integral e purê de batata', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 16,
     'short_description': 'Parmegiana tradicional extremamente deliciosa! FICHA TÉCNICA: 120g de filé grelhado; 100g de arroz integral; 130g de purê de batata; 30g…',
     'description': 'Parmegiana tradicional extremamente deliciosa! FICHA TÉCNICA: 120g de filé grelhado; 100g de arroz integral; 130g de purê de batata; 30g queijo mussarela zero PORÇÃO: 350g',
     'image': 'parmegiana-de-frango-com-arroz-integral-e-pure-de-batata.png',
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-17', 'category_slug': 'linha-fit', 'name': 'Patinho moído, arroz, feijão e banana da terra e couve refogada', 'price': Decimal('24.00'), 'featured': False, 'sort_order': 17,
     'short_description': '',
     'description': 'Porção: 120g de patinho moído 80g de feijão 130g de arroz~20g de couve refogada',
     'image': 'patinho-moido-arroz-feijao-e-banana-da-terra-e-couve-refogada.webp',
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-18', 'category_slug': 'linha-fit', 'name': 'Picadinho de panela com mandioca, couve e arroz', 'price': Decimal('24.00'), 'featured': False, 'sort_order': 18,
     'short_description': 'Clássico e delicioso picadinho de panela com arroz branco, mandioca cozida e couve.',
     'description': 'Clássico e delicioso picadinho de panela com arroz branco, mandioca cozida e couve. Opção maravilhosa para comer bem na semana e no dia-a-dia! Prático e saboroso! Porção: Picadinho de panela 120g Mandioca 60g Couve e alho ~30g Arroz 100g',
     'image': 'picadinho-de-panela-com-mandioca-couve-e-arroz.webp',
     'tags': ['linha-fit']},
    {'sku': 'AGR-FIT-19', 'category_slug': 'linha-fit', 'name': 'Carne desfiada com arroz branco e feijão carioca e couve flor', 'price': Decimal('24.00'), 'featured': False, 'sort_order': 19,
     'short_description': 'Deliciosa carne desfiada suculenta, acompanhada de arroz branco e um feijão carioca e couve-flor cozida á vapor.',
     'description': 'Deliciosa carne desfiada suculenta, acompanhada de arroz branco e um feijão carioca e couve-flor cozida á vapor. Opção perfeita para sua semana, praticidade e sabor para o seu dia-a-dia! Porção: 120g carne desfiada 110g arroz branco 20g de couve-flor 1 concha (~80g) de feijão carioca',
     'image': None,
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-20', 'category_slug': 'linha-fit', 'name': 'Carne desfiada com arroz branco e feijão preto e couve', 'price': Decimal('24.00'), 'featured': False, 'sort_order': 20,
     'short_description': 'Deliciosa carne desfiada suculenta, acompanhada de arroz branco e um feijão preto e couve refogada.',
     'description': 'Deliciosa carne desfiada suculenta, acompanhada de arroz branco e um feijão preto e couve refogada. Opção perfeita para sua semana, praticidade e sabor para o seu dia-a- dia! Porção: 120g carne desfiada 110g (230g somado)20g de couve refogada 1 concha (~80g) de feijão preto',
     'image': None,
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-21', 'category_slug': 'linha-fit', 'name': 'Carne desfiada com arroz branco e feijão preto e couve flor', 'price': Decimal('24.00'), 'featured': False, 'sort_order': 21,
     'short_description': 'Deliciosa carne desfiada suculenta, acompanhada de arroz branco e um feijão preto e couve-flor cozida á vapor.',
     'description': 'Deliciosa carne desfiada suculenta, acompanhada de arroz branco e um feijão preto e couve-flor cozida á vapor. Opção perfeita para sua semana, praticidade e sabor para o seu dia-a-dia! Porção: 120g carne desfiada 110g arroz branco 20g de couve-flor 1 concha (~80g) de feijão preto',
     'image': None,
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-22', 'category_slug': 'linha-fit', 'name': 'Frango desfiado, arroz branco e feijao preto', 'price': Decimal('23.00'), 'featured': False, 'sort_order': 22,
     'short_description': 'Frango desfiado ao tempero caseiro, servido com arroz branco soltinho e feijão preto bem temperado.',
     'description': 'Frango desfiado ao tempero caseiro, servido com arroz branco soltinho e feijão preto bem temperado. Uma combinação tradicional, prática e saborosa para sua semana. Porção total: 330 g 120 g de frango desfiado 130 g de arroz branco 80 g de feijão preto',
     'image': None,
     'tags': ['frango', 'linha-fit']},
    {'sku': 'AGR-FIT-23', 'category_slug': 'linha-fit', 'name': 'Patinho moído, arroz com cúrcuma e feijão carioca', 'price': Decimal('24.00'), 'featured': False, 'sort_order': 23,
     'short_description': 'Patinho moído suculento e bem temperado, servido com arroz aromático com cúrcuma e feijão carioca ao tempero caseiro.',
     'description': 'Patinho moído suculento e bem temperado, servido com arroz aromático com cúrcuma e feijão carioca ao tempero caseiro. Uma combinação clássica e perfeita para o dia a dia. Porção total: 330 g 120 g de patinho moído 130 g de arroz com cúrcuma 80 g de feijão carioca',
     'image': None,
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-FIT-24', 'category_slug': 'linha-fit', 'name': 'Patinho moído, arroz, brócolis gratinado', 'price': Decimal('24.00'), 'featured': False, 'sort_order': 24,
     'short_description': 'Patinho moído ao tempero caseiro, acompanhado de arroz soltinho e brocolis gratinado.',
     'description': 'Patinho moído ao tempero caseiro, acompanhado de arroz soltinho e brocolis gratinado. Uma refeição equilibrada, colorida e saborosa para facilitar sua rotina. Porção: 120g patinho moído 130g de arroz branco 80g de brócolis gratinado (com molho 3 queijos)Porção total: 310 g',
     'image': None,
     'tags': ['carne', 'linha-fit']},
    {'sku': 'AGR-BIS-01', 'category_slug': 'linha-bistro', 'name': 'CONCHIGLIONE DE FRANGO COM MOLHO RUSTICO DE TOMATE', 'price': Decimal('37.90'), 'featured': True, 'sort_order': 1,
     'short_description': 'Conchiglione de grano duro recheado com um cremoso preparo de frango e queijos, coberto com molho rústico de tomate e finalizado com…',
     'description': 'Conchiglione de grano duro recheado com um cremoso preparo de frango e queijos, coberto com molho rústico de tomate e finalizado com parmesão. Um prato clássico, cremoso e cheio de sabor, inspirado na tradicional culinária italiana. INGREDIENTES Conchiglione, grano duro, tomate, peito de frango, creme de leite, queijo muçarela, queijo parmesão, ricota, cebola, vinagrete desidratado, sal refinado, azeite extra virgem, manjericão, manteiga, requeijão cremoso e molho pomarola.',
     'image': 'conchiglione-de-frango-com-molho-rustico-de-tomate.png',
     'tags': ['frango', 'linha-bistro']},
    {'sku': 'AGR-BIS-02', 'category_slug': 'linha-bistro', 'name': 'Galinhada com Feijão fradinho 440g', 'price': Decimal('46.00'), 'featured': True, 'sort_order': 2,
     'short_description': '',
     'description': '',
     'image': 'galinhada-com-feijao-fradinho-440g.webp',
     'tags': ['linha-bistro']},
    {'sku': 'AGR-BIS-03', 'category_slug': 'linha-bistro', 'name': 'PIRARUCU COM CROSTA DE CASTANHAS, MOLHO DE MOQUECA, PURÊ DE BANANA-DA-TERRA E ARROZ BRANCO – 440g', 'price': Decimal('46.00'), 'featured': False, 'sort_order': 3,
     'short_description': 'Filé de pirarucu com crosta crocante de castanhas brasileiras, servido com um delicado molho de moqueca, purê cremoso de banana-da-terra e…',
     'description': 'Filé de pirarucu com crosta crocante de castanhas brasileiras, servido com um delicado molho de moqueca, purê cremoso de banana-da-terra e arroz branco soltinho. Uma combinação que valoriza os sabores da culinária brasileira, equilibrada e cheia de personalidade. Ingredientes: Filé de pirarucu, banana-da-terra, arroz branco, creme de leite, leite de coco, molho de tomate, pimentão vermelho, pimentão amarelo, castanha- de-caju, farinha panko, manteiga, queijo parmesão, óleo de soja, alho, cebola, coentro, salsa, azeite de dendê, tempero tártaro desidratado, lemon pepper, vinagre, sal, açúcar, pimenta-de-cheiro e pimenta-do-reino. Alérgicos: CONTÉM LEITE E DERIVADOS, GLÚTEN (TRIGO), DERIVADOS DE SOJA E CASTANHA-DE-CAJU. PODE CONTER AVEIA, CEVADA, CENTEIO E AMENDOIM.',
     'image': 'pirarucu-com-crosta-de-castanhas-molho-de-moqueca-pure-de-banana-da-te.webp',
     'tags': ['peixe', 'linha-bistro']},
    {'sku': 'AGR-BIS-04', 'category_slug': 'linha-bistro', 'name': 'Panquecas Artesanais de Frango com Palmito e Requeijão ao Molho Quatro Queijos 440g', 'price': Decimal('38.00'), 'featured': False, 'sort_order': 4,
     'short_description': 'Duas panquecas artesanais recheadas com frango desfiado, palmito e requeijão cremoso, cobertas com um irresistível molho quatro queijos…',
     'description': 'Duas panquecas artesanais recheadas com frango desfiado, palmito e requeijão cremoso, cobertas com um irresistível molho quatro queijos, preparado com parmesão, provolone, gorgonzola e molho béchamel. Um prato cremoso, sofisticado e cheio de sabor. Ingredientes: Leite integral, peito de frango, creme de leite, farinha de trigo enriquecida com ferro e ácido fólico, palmito, ovos, requeijão cremoso, cebola, manteiga, queijo provolone, queijo parmesão, queijo gorgonzola, cebolinha, sal, vinagrete desidratado e pimenta-do-reino. Alérgicos: CONTÉM GLÚTEN, LEITE E DERIVADOS, OVO E DERIVADOS DE TRIGO. PODE CONTER DERIVADOS DE SOJA E AMENDOIM.',
     'image': 'panquecas-artesanais-de-frango-com-palmito-e-requeijao-ao-molho-quatro.webp',
     'tags': ['frango', 'linha-bistro']},
    {'sku': 'AGR-BIS-05', 'category_slug': 'linha-bistro', 'name': 'Panquecas Artesanais de carne moida com azeitona e molho pomodoro 440g', 'price': Decimal('38.00'), 'featured': False, 'sort_order': 5,
     'short_description': 'Três panquecas artesanais recheadas com carne bovina bem temperada, azeitonas e queijo muçarela, cobertas com molho pomodoro caseiro e…',
     'description': 'Três panquecas artesanais recheadas com carne bovina bem temperada, azeitonas e queijo muçarela, cobertas com molho pomodoro caseiro e finalizadas com salsa fresca. Um clássico caseiro, suculento e cheio de sabor. Ingredientes: Carne bovina (patinho), tomate pelado, molho de tomate, alho, cebola, salsa fresca, sal, pimenta-do-reino, farinha de trigo enriquecida com ferro e ácido fólico, leite integral, ovos, óleo de soja, azeite de oliva, queijo muçarela e azeitonas verdes. Alérgicos: CONTÉM GLÚTEN, LEITE E DERIVADOS, OVO E DERIVADOS DE SOJA. PODE CONTER AMENDOIM.',
     'image': 'panquecas-artesanais-de-carne-moida-com-azeitona-e-molho-pomodoro-440g.webp',
     'tags': ['carne', 'linha-bistro']},
    {'sku': 'AGR-BIS-06', 'category_slug': 'linha-bistro', 'name': 'Risoto de funghi e tornrdor de filé mignon ao molho de vinho', 'price': Decimal('48.00'), 'featured': False, 'sort_order': 6,
     'short_description': 'Arroz arbóreo, filé mignon, funghi, vinho tinto, cebola, alho, manteiga, creme de leite, queijo parmesão, azeite de oliva, caldo de…',
     'description': 'Arroz arbóreo, filé mignon, funghi, vinho tinto, cebola, alho, manteiga, creme de leite, queijo parmesão, azeite de oliva, caldo de legumes, sal e pimenta-do-reino. Alérgicos: Contém leite e derivados. Pode conter traços de glúten. 440g',
     'image': 'risoto-de-funghi-e-tornrdor-de-file-mignon-ao-molho-de-vinho.webp',
     'tags': ['caldo', 'linha-bistro']},
    {'sku': 'AGR-BIS-07', 'category_slug': 'linha-bistro', 'name': 'STROGONOFF DE FRANGO COM ARROZ BRANCO E BRÓCOLIS', 'price': Decimal('38.00'), 'featured': False, 'sort_order': 7,
     'short_description': 'Clássico estrogonofe de frango, cremoso e suave, servido com arroz branco soltinho e brócolis levemente al dente.',
     'description': 'Clássico estrogonofe de frango, cremoso e suave, servido com arroz branco soltinho e brócolis levemente al dente. Uma releitura saudável do prato queridinho dos brasileiros. Cremoso na medida certa, com o toque especial do brócolis e o arroz leve para completar a refeição. Contem Glúten',
     'image': 'strogonoff-de-frango-com-arroz-branco-e-brocolis.webp',
     'tags': ['frango', 'linha-bistro']},
    {'sku': 'AGR-BIS-08', 'category_slug': 'linha-bistro', 'name': 'Talharim ao molho bolonhesa e queijo mussarela 440G', 'price': Decimal('38.00'), 'featured': False, 'sort_order': 8,
     'short_description': 'Deliciosa massa de talharim acompanhada com molho bolonhesa e mussarela, perfeito para quem ama massas e um molho vermelho.',
     'description': 'Deliciosa massa de talharim acompanhada com molho bolonhesa e mussarela, perfeito para quem ama massas e um molho vermelho. Uma ótima opção para um jantar leve, prático e com muito sabor. Porção: 200g de talharim 220g de molho bolonhesa com patinho moído 20g de mussarela',
     'image': 'talharim-ao-molho-bolonhesa-e-queijo-mussarela-440g.webp',
     'tags': ['carne', 'doce', 'linha-bistro']},
    {'sku': 'AGR-BIS-09', 'category_slug': 'linha-bistro', 'name': 'Franguinho Goiano Com Pure De Batata', 'price': Decimal('38.00'), 'featured': False, 'sort_order': 9,
     'short_description': '',
     'description': '',
     'image': None,
     'tags': ['linha-bistro']},
    {'sku': 'AGR-CAL-01', 'category_slug': 'caldos-fit', 'name': 'CALDO DE PINTO', 'price': Decimal('15.00'), 'featured': True, 'sort_order': 1,
     'short_description': '',
     'description': 'Porção: 350ml Produto congelado Ingredientes: Frango, mandioca, batata inglesa, tomate, cebola, alho, pimenta-de-cheiro, páprica doce, cheiro-verde e sal.',
     'image': 'caldo-de-pinto.webp',
     'tags': ['frango', 'caldo', 'caldos-fit']},
    {'sku': 'AGR-CAL-02', 'category_slug': 'caldos-fit', 'name': 'CALDO DETOX', 'price': Decimal('15.00'), 'featured': True, 'sort_order': 2,
     'short_description': '',
     'description': 'Porção: 350ml Produto congelado Ingredientes: Frango, legumes.',
     'image': 'caldo-detox.webp',
     'tags': ['frango', 'caldo', 'caldos-fit']},
    {'sku': 'AGR-CAL-03', 'category_slug': 'caldos-fit', 'name': 'CALDO VERDE', 'price': Decimal('15.00'), 'featured': False, 'sort_order': 3,
     'short_description': 'Caldo low carb - contém bacon e mix de folhas',
     'description': 'Caldo low carb - contém bacon e mix de folhas',
     'image': 'caldo-verde.webp',
     'tags': ['caldo', 'caldos-fit']},
    {'sku': 'AGR-CAL-04', 'category_slug': 'caldos-fit', 'name': 'Caldo de Patinho com Abóbora', 'price': Decimal('15.00'), 'featured': False, 'sort_order': 4,
     'short_description': '',
     'description': 'Porção: 350ml Produto congelado Ingredientes: Patinho bovino, abóbora cabotiá, cenoura, cebola, alho, pimenta-de-cheiro, gengibre, salsa, cheiro-verde e sal.',
     'image': 'caldo-de-patinho-com-abobora.webp',
     'tags': ['carne', 'caldo', 'caldos-fit']},
    {'sku': 'AGR-SOB-01', 'category_slug': 'sobremesas-artelatto', 'name': 'Doce de leite ZERO', 'price': Decimal('18.00'), 'featured': True, 'sort_order': 1,
     'short_description': 'Doce de leite Creme de leite zero lactose • Xilitol • Polidextrose 289 Kcal pote com 60 gramas',
     'description': 'Doce de leite Creme de leite zero lactose • Xilitol • Polidextrose 289 Kcal pote com 60 gramas INGREDIENTES: Creme de leite zero lactose, xilitol cristalizado. ZERO LACTOSE NÃO CONTÉM GLÚTEN',
     'image': 'doce-de-leite-zero.webp',
     'tags': ['sobremesas-artelatto']},
    {'sku': 'AGR-SOB-02', 'category_slug': 'sobremesas-artelatto', 'name': 'Sobremesa Gelada - Abacaxi com Coco', 'price': Decimal('16.00'), 'featured': True, 'sort_order': 2,
     'short_description': 'Sobremesa gelada - Saborosa, cremosa e extremamente deliciosa. Sobremesa de abacaxi com coco!',
     'description': 'Sobremesa gelada - Saborosa, cremosa e extremamente deliciosa. Sobremesa de abacaxi com coco!',
     'image': 'sobremesa-gelada-abacaxi-com-coco.webp',
     'tags': ['doce', 'sobremesas-artelatto']},
    {'sku': 'AGR-SOB-03', 'category_slug': 'sobremesas-artelatto', 'name': 'Sobremesa Gelada - Banoffe', 'price': Decimal('16.00'), 'featured': False, 'sort_order': 3,
     'short_description': 'Banoffee Uma sobremesa irresistível em camadas, com a combinação perfeita de doce de leite, banana e um creme incrivelmente suave.',
     'description': 'Banoffee Uma sobremesa irresistível em camadas, com a combinação perfeita de doce de leite, banana e um creme incrivelmente suave. Uma delícia para comer de colher!',
     'image': 'sobremesa-gelada-banoffe.webp',
     'tags': ['doce', 'sobremesas-artelatto']},
    {'sku': 'AGR-SOB-04', 'category_slug': 'sobremesas-artelatto', 'name': 'Sobremesa Gelada - Caramelo salgado com paçoca', 'price': Decimal('16.00'), 'featured': False, 'sort_order': 4,
     'short_description': '',
     'description': '',
     'image': 'sobremesa-gelada-caramelo-salgado-com-pacoca.webp',
     'tags': ['doce', 'sobremesas-artelatto']},
    {'sku': 'AGR-SOB-05', 'category_slug': 'sobremesas-artelatto', 'name': 'Sobremesa Gelada - Ninho com Nutella', 'price': Decimal('16.00'), 'featured': False, 'sort_order': 5,
     'short_description': '',
     'description': '',
     'image': 'sobremesa-gelada-ninho-com-nutella.png',
     'tags': ['doce', 'sobremesas-artelatto']},
    {'sku': 'AGR-SOB-06', 'category_slug': 'sobremesas-artelatto', 'name': 'BOLO FATIADO', 'price': Decimal('25.00'), 'featured': False, 'sort_order': 6,
     'short_description': '',
     'description': '',
     'image': None,
     'tags': ['doce', 'sobremesas-artelatto']},
    {'sku': 'AGR-SOB-07', 'category_slug': 'sobremesas-artelatto', 'name': 'BOLO FATIADO GOURMET', 'price': Decimal('0.00'), 'featured': False, 'sort_order': 7,
     'short_description': '',
     'description': '',
     'image': None,
     'tags': ['doce', 'sobremesas-artelatto']},
    {'sku': 'AGR-SOB-08', 'category_slug': 'sobremesas-artelatto', 'name': 'Brownie com Doce de Leite', 'price': Decimal('16.00'), 'featured': False, 'sort_order': 8,
     'short_description': 'Delicioso brownie no pote recheado com crema de ninho e doce de leite caseiro! Sabor irresistível! CONTÉM AÇÚCARCONTÉM LACTOSE',
     'description': 'Delicioso brownie no pote recheado com crema de ninho e doce de leite caseiro! Sabor irresistível! CONTÉM AÇÚCARCONTÉM LACTOSE',
     'image': None,
     'tags': ['doce', 'sobremesas-artelatto']},
    {'sku': 'AGR-SOB-09', 'category_slug': 'sobremesas-artelatto', 'name': 'Brownie com crema de ninho', 'price': Decimal('16.00'), 'featured': False, 'sort_order': 9,
     'short_description': 'Delicioso brownie no pote recheado com crema de ninho caseira! Sabor irresistível! CONTÉM AÇÚCARCONTÉM LACTOSE',
     'description': 'Delicioso brownie no pote recheado com crema de ninho caseira! Sabor irresistível! CONTÉM AÇÚCARCONTÉM LACTOSE',
     'image': None,
     'tags': ['doce', 'sobremesas-artelatto']},
    {'sku': 'AGR-SOB-10', 'category_slug': 'sobremesas-artelatto', 'name': 'Brownie com crema de nutella', 'price': Decimal('16.00'), 'featured': False, 'sort_order': 10,
     'short_description': '',
     'description': '',
     'image': None,
     'tags': ['doce', 'sobremesas-artelatto']},
]


class Command(BaseCommand):
    help = 'Popula a loja Agrião Comida Saudável (4 linhas, produtos disponíveis)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Mostra o que seria feito sem gravar nada')

    def handle(self, *args, **options):
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('🔍 DRY-RUN — nada será gravado\n'))
            missing = [p['name'] for p in PRODUCTS if not p.get('image')]
            self.stdout.write(f'Store: {STORE_SLUG} | Categorias: {len(CATEGORIES)} | Produtos: {len(PRODUCTS)}')
            self.stdout.write(f'Produtos sem foto: {len(missing)}')
            for n in missing:
                self.stdout.write(f'  - {n}')
            base = Path(settings.MEDIA_ROOT) / IMG_PATH
            ausentes = [p['image'] for p in PRODUCTS if p.get('image') and not (base / p['image']).exists()]
            self.stdout.write(self.style.ERROR(f'Arquivos de imagem ausentes em disco: {len(ausentes)}'))
            for a in ausentes:
                self.stdout.write(f'  ! {a}')
            return
        self._run()

    @transaction.atomic
    def _run(self):
        self.stdout.write('📋 Fase 1: Store...')
        owner = User.objects.filter(email__iexact=OWNER_EMAIL).first()
        if owner is None:
            owner = User.objects.filter(is_superuser=True).first()
            self.stdout.write(self.style.WARNING(
                f'⚠️  Nenhum usuário com {OWNER_EMAIL} — usando {owner} como owner provisório'))
        if owner is None:
            self.stdout.write(self.style.ERROR('❌ Nenhum usuário disponível para ser owner'))
            return

        store, created = Store.objects.get_or_create(
            slug=STORE_SLUG,
            defaults={'name': 'Agrião Comida Saudável', 'owner': owner,
                      'store_type': Store.StoreType.FOOD},
        )
        # Identidade e operação vindas do cardápio impresso.
        store.name = 'Agrião Comida Saudável'
        store.description = ('Comida saudável congelada em Palmas. Refeições equilibradas da Linha Fit, '
                             'pratos elaborados da Linha Bistrô, caldos e sobremesas artesanais — '
                             'é só esquentar e comer bem.')
        store.tagline = 'Comida de verdade, pronta em minutos.'
        store.store_type = Store.StoreType.FOOD
        store.status = Store.StoreStatus.ACTIVE
        store.is_active = True
        store.template = 'fresh'
        store.currency = 'BRL'
        store.timezone = 'America/Sao_Paulo'
        store.email = OWNER_EMAIL
        store.phone = '(63) 99954-7790'
        store.whatsapp_number = '5563999547790'
        store.address = 'Quadra ASR SE 15, Rua SR 1, nº 06 - Plano Diretor Sul'
        store.city = 'Palmas'
        store.state = 'TO'
        store.zip_code = '77020-170'
        store.country = 'BR'
        store.delivery_enabled = True
        store.pickup_enabled = True
        store.operating_hours = OPERATING_HOURS
        # Verde do logo (agrião).
        store.primary_color = '#026600'
        store.secondary_color = '#3D883C'

        logo_path = Path(settings.MEDIA_ROOT) / IMG_PATH / LOGO_FILE
        if logo_path.exists():
            optimized = ImageOptimizer().optimize(str(logo_path), max_width=512, max_height=512)
            if optimized:
                store.logo_url = f"{settings.MEDIA_URL.rstrip('/')}/{IMG_PATH}/{Path(optimized).name}"

        meta = dict(store.metadata or {})
        meta['seed_source'] = 'populate_agriao_comida_saudavel_menu'
        store.metadata = meta
        store.save()
        self.stdout.write(self.style.SUCCESS(
            f'{"✅ Store criada" if created else "🔄 Store atualizada"}: {store.name} ({store.slug})'))

        self.stdout.write('📋 Fase 2: Categorias...')
        category_map = {}
        for cat in CATEGORIES:
            obj, _ = StoreCategory.objects.update_or_create(
                store=store, slug=cat['slug'],
                defaults={'name': cat['name'], 'description': cat['description'],
                          'sort_order': cat['sort_order'], 'is_active': True},
            )
            category_map[cat['slug']] = obj
        self.stdout.write(self.style.SUCCESS(f'✅ {len(CATEGORIES)} categoria(s)'))

        self.stdout.write('📋 Fase 3: Produtos (com otimização de imagens)...')
        optimizer = ImageOptimizer()
        optimized_count = 0
        sem_foto = []
        for prod in PRODUCTS:
            image_url = ''
            filename = prod.get('image')
            if filename:
                image_path = Path(settings.MEDIA_ROOT) / IMG_PATH / filename
                if image_path.exists():
                    optimized_path = optimizer.optimize(str(image_path))
                    if optimized_path:
                        optimized_count += 1
                        image_url = f"{settings.MEDIA_URL.rstrip('/')}/{IMG_PATH}/{Path(optimized_path).name}"
                else:
                    self.stdout.write(self.style.WARNING(f'  ⚠️  Imagem ausente: {filename}'))
            else:
                sem_foto.append(prod['name'])

            StoreProduct.objects.update_or_create(
                store=store, slug=slugify(prod['name']),
                defaults={
                    'category': category_map.get(prod['category_slug']),
                    'name': prod['name'],
                    'short_description': prod.get('short_description', ''),
                    'description': prod.get('description', ''),
                    'price': prod['price'],
                    'sku': prod['sku'],
                    'featured': prod.get('featured', False),
                    'sort_order': prod['sort_order'],
                    'main_image_url': image_url,
                    'tags': prod.get('tags', []),
                    'track_stock': False,
                    'is_active': prod['price'] > 0,
                },
            )
        self.stdout.write(self.style.SUCCESS(
            f'✅ {len(PRODUCTS)} produto(s), {optimized_count} imagem(ns) otimizada(s)'))

        zerados = [p['name'] for p in PRODUCTS if p['price'] <= 0]
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('✅ POPULAÇÃO CONCLUÍDA'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'Store: {store.name} ({store.slug}) — owner {owner}')
        self.stdout.write(f'Categorias: {len(CATEGORIES)} | Produtos: {len(PRODUCTS)}')
        if sem_foto:
            self.stdout.write(self.style.WARNING(f'\n⚠️  {len(sem_foto)} produto(s) sem foto (o cardápio de origem não tem):'))
            for n in sem_foto:
                self.stdout.write(f'   - {n}')
        if zerados:
            self.stdout.write(self.style.WARNING(f'\n⚠️  {len(zerados)} produto(s) com preço R$ 0,00 — criados INATIVOS:'))
            for n in zerados:
                self.stdout.write(f'   - {n}')
