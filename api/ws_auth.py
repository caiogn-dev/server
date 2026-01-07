from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.db import close_old_connections


@database_sync_to_async
def get_user_from_token(token_key: str):
    from django.contrib.auth.models import AnonymousUser
    from rest_framework.authtoken.models import Token
    try:
        token = Token.objects.select_related("user").get(key=token_key)
        return token.user
    except Token.DoesNotExist:
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        close_old_connections()
        from django.contrib.auth.models import AnonymousUser
        token_key = None
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token_key = query_params.get("token", [None])[0]

        if not token_key:
            headers = dict(scope.get("headers") or [])
            auth_header = headers.get(b"authorization")
            if auth_header and auth_header.lower().startswith(b"token "):
                token_key = auth_header.split(b" ", 1)[1].decode()

        if token_key:
            scope["user"] = await get_user_from_token(token_key)
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
