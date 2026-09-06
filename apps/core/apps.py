from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'

    def ready(self):
        # Liga o CORS ao cadastro da loja. Antes disto, a lista de origens era
        # estática numa variável de ambiente: todo cliente novo com domínio
        # próprio — que é o que o produto VENDE — precisava de uma edição de
        # env e um restart, e até lá via a própria loja abrir e não carregar
        # nada. Ver `apps/core/cors.py`.
        from corsheaders.signals import check_request_enabled
        from django.db.models.signals import post_delete, post_save

        from .cors import esquecer_dominios_de_loja, liberar_dominio_de_loja

        check_request_enabled.connect(liberar_dominio_de_loja)

        # A lista de domínios é cacheada — ela roda em TODA requisição com
        # `Origin`. Sem invalidar ao salvar, o dono digita o domínio, testa na
        # hora e vê a loja continuar quebrada por cinco minutos.
        #
        # `sender` como string evita importar `Store` aqui: `ready()` roda antes
        # do registro de apps terminar, e o import derruba a subida.
        post_save.connect(esquecer_dominios_de_loja, sender='stores.Store')
        post_delete.connect(esquecer_dominios_de_loja, sender='stores.Store')
