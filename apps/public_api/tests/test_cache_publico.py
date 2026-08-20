"""O cardápio público precisa poder ser servido da borda."""
from django.http import JsonResponse
from django.test import TestCase, RequestFactory

from apps.public_api.cache import cache_publico


class CachePublicoTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _resposta(self, status=200, segundos=60):
        @cache_publico(segundos)
        def view(request):
            return JsonResponse({'ok': True}, status=status)
        return view(self.rf.get('/qualquer/'))

    def test_resposta_boa_vira_cacheavel_na_borda(self):
        cc = self._resposta()['Cache-Control']
        self.assertIn('public', cc)
        self.assertIn('s-maxage=60', cc)
        self.assertIn('stale-while-revalidate', cc)

    def test_nao_usa_max_age_para_o_navegador(self):
        """`max-age` prenderia o LOJISTA na versão velha ao editar um produto.
        Só a borda deve cachear; o navegador continua revalidando."""
        cc = self._resposta()['Cache-Control']
        self.assertNotRegex(cc, r'(^|[, ])max-age=')

    def test_erro_nao_e_cacheado(self):
        """404/500 na borda multiplica um erro momentâneo por todo o TTL."""
        self.assertNotIn('Cache-Control', self._resposta(status=404))
        self.assertNotIn('Cache-Control', self._resposta(status=500))

    def test_ttl_configuravel(self):
        self.assertIn('s-maxage=300', self._resposta(segundos=300)['Cache-Control'])
