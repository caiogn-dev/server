"""Tests for RequestLoggingMiddleware log-level routing.

Garante que:
- 2xx em endpoints normais -> INFO
- 2xx em endpoints de polling de alta frequência (quiet paths) -> DEBUG
- respostas de erro (>=400) -> WARNING (independente do path)
"""
from unittest import mock

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.core.middleware import RequestLoggingMiddleware


def _middleware(status_code=200):
    return RequestLoggingMiddleware(lambda request: HttpResponse(status=status_code))


class RequestLoggingMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_normal_2xx_logs_info(self):
        mw = _middleware(200)
        with mock.patch('apps.core.middleware.logger') as log:
            mw(self.factory.get('/api/v1/stores/some-store/orders/'))
        log.info.assert_called_once()
        log.debug.assert_not_called()
        log.warning.assert_not_called()

    def test_quiet_path_2xx_logs_debug_not_info(self):
        mw = _middleware(200)
        with mock.patch('apps.core.middleware.logger') as log:
            mw(self.factory.post('/api/v1/stores/print/agent/claim-next/'))
        log.debug.assert_called_once()
        log.info.assert_not_called()
        log.warning.assert_not_called()

    def test_health_quiet_path_2xx_logs_debug(self):
        mw = _middleware(200)
        with mock.patch('apps.core.middleware.logger') as log:
            mw(self.factory.get('/api/sse/health/'))
        log.debug.assert_called_once()
        log.info.assert_not_called()

    def test_error_on_quiet_path_still_warns(self):
        mw = _middleware(500)
        with mock.patch('apps.core.middleware.logger') as log:
            mw(self.factory.post('/api/v1/stores/print/agent/claim-next/'))
        log.warning.assert_called_once()
        log.debug.assert_not_called()
        log.info.assert_not_called()

    def test_4xx_logs_warning(self):
        mw = _middleware(404)
        with mock.patch('apps.core.middleware.logger') as log:
            mw(self.factory.get('/api/v1/stores/whatever/'))
        log.warning.assert_called_once()
        log.info.assert_not_called()

    @override_settings(REQUEST_LOG_QUIET_PATHS=('/custom/quiet',))
    def test_quiet_paths_configurable_via_settings(self):
        mw = _middleware(200)
        with mock.patch('apps.core.middleware.logger') as log:
            mw(self.factory.get('/custom/quiet/poll/'))
        log.debug.assert_called_once()
        log.info.assert_not_called()
        # default path is no longer quiet when overridden
        with mock.patch('apps.core.middleware.logger') as log2:
            mw2 = _middleware(200)
            mw2(self.factory.post('/api/v1/stores/print/agent/claim-next/'))
        log2.info.assert_called_once()
        log2.debug.assert_not_called()

    def test_response_has_request_id_header(self):
        mw = _middleware(200)
        resp = mw(self.factory.get('/api/sse/health/'))
        assert resp['X-Request-ID']
