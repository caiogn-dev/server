"""
Webhook Alert Service

Envia alertas para Slack, Discord, ou sistema de monitoramento
quando há falhas massivas em webhooks.
"""
import json
import logging
from typing import Optional
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class WebhookAlertService:
    """
    Serviço de alertas para monitoramento de webhooks.
    
    Envia notificações quando:
    - Falhas massivas (>50 em 1 hora)
    - Falhas críticas (>100 em 1 hora)
    - Sistema emergencial (>500 falhas)
    """
    
    DEFAULT_WEBHOOK_URL: Optional[str] = getattr(settings, 'ALERT_WEBHOOK_URL', None)
    ALERT_THRESHOLD_WARNING = 50
    ALERT_THRESHOLD_CRITICAL = 100
    ALERT_THRESHOLD_EMERGENCY = 500
    
    @classmethod
    def send_slack_alert(cls, message: str, level: str = 'warning', details: dict = None) -> bool:
        """
        Envia alerta para Slack via webhook.
        
        Args:
            message: Mensagem do alerta
            level: Nível (warning, critical, emergency)
            details: Detalhes adicionais
            
        Returns:
            bool: Sucesso do envio
        """
        webhook_url = cls.DEFAULT_WEBHOOK_URL
        
        if not webhook_url:
            logger.warning("[AlertService] ALERT_WEBHOOK_URL not configured")
            return False
        
        color_map = {
            'warning': '#ffcc00',
            'critical': '#ff6600',
            'emergency': '#ff0000',
        }
        
        emoji_map = {
            'warning': ':warning:',
            'critical': ':rotating_light:',
            'emergency': ':fire:',
        }
        
        payload = {
            "attachments": [
                {
                    "color": color_map.get(level, '#cccccc'),
                    "title": f"{emoji_map.get(level, '')} Webhook Alert - {level.upper()}",
                    "text": message,
                    "footer": "Pastita Platform",
                    "fields": []
                }
            ]
        }
        
        if details:
            for key, value in details.items():
                payload["attachments"][0]["fields"].append({
                    "title": key,
                    "value": str(value),
                    "short": True
                })
        
        try:
            response = requests.post(
                webhook_url,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"[AlertService] Alert sent: {level} - {message[:50]}...")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"[AlertService] Failed to send alert: {e}")
            return False
    
    @classmethod
    def check_failure_rate(cls, recent_failures: int, time_window_minutes: int = 60) -> str:
        """
        Verifica taxa de falhas e retorna nível de alerta.
        
        Args:
            recent_failures: Número de falhas recentes
            time_window_minutes: Janela de tempo em minutos
            
        Returns:
            str: Nível de alerta ou None
        """
        if recent_failures >= cls.ALERT_THRESHOLD_EMERGENCY:
            return 'emergency'
        elif recent_failures >= cls.ALERT_THRESHOLD_CRITICAL:
            return 'critical'
        elif recent_failures >= cls.ALERT_THRESHOLD_WARNING:
            return 'warning'
        return None
    
    @classmethod
    def send_failure_alert(cls, failure_count: int, time_window: int = 60):
        """
        Envia alerta baseado no número de falhas.
        
        Args:
            failure_count: Número de falhas detectadas
            time_window: Janela de tempo em minutos
        """
        level = cls.check_failure_rate(failure_count, time_window)
        
        if not level:
            return
        
        message = f"Detected {failure_count} webhook failures in the last {time_window} minutes"
        
        details = {
            "Failure Count": failure_count,
            "Time Window": f"{time_window} min",
            "Threshold": getattr(cls, f'ALERT_THRESHOLD_{level.upper()}', 0),
        }
        
        cls.send_slack_alert(message, level, details)
