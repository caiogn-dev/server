"""
Langflow Service - Integration with Langflow LLM platform.
"""
import logging
import time
import uuid
import requests
from typing import Dict, Any, Optional, List
from django.conf import settings
from django.utils import timezone
from apps.core.exceptions import LangflowAPIError, NotFoundError
from ..models import LangflowFlow, LangflowSession, LangflowLog

logger = logging.getLogger(__name__)


class LangflowService:
    """Service for Langflow integration."""

    def __init__(self):
        self.base_url = settings.LANGFLOW_API_URL
        self.api_key = settings.LANGFLOW_API_KEY

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            'Content-Type': 'application/json',
        }
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Make HTTP request to Langflow API."""
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                timeout=timeout
            )
            
            response_data = response.json() if response.content else {}
            
            if response.status_code >= 400:
                logger.error(
                    f"Langflow API error: {response.status_code}",
                    extra={
                        'status_code': response.status_code,
                        'endpoint': endpoint,
                        'response': response_data,
                    }
                )
                raise LangflowAPIError(
                    message=response_data.get('detail', 'Langflow API error'),
                    code=str(response.status_code),
                    details=response_data
                )
            
            return response_data
            
        except requests.exceptions.Timeout:
            logger.error(f"Langflow API timeout: {endpoint}")
            raise LangflowAPIError(
                message="Langflow API timeout",
                code='timeout'
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Langflow API request failed: {str(e)}")
            raise LangflowAPIError(
                message=f"Request failed: {str(e)}",
                code='request_failed'
            )

    def get_flow(self, flow_id: str) -> LangflowFlow:
        """Get flow by ID."""
        try:
            return LangflowFlow.objects.get(id=flow_id, is_active=True)
        except LangflowFlow.DoesNotExist:
            raise NotFoundError(message="Langflow flow not found")

    def get_flow_by_external_id(self, external_flow_id: str) -> LangflowFlow:
        """Get flow by external Langflow ID."""
        try:
            return LangflowFlow.objects.get(flow_id=external_flow_id, is_active=True)
        except LangflowFlow.DoesNotExist:
            raise NotFoundError(message="Langflow flow not found")

    def get_or_create_session(
        self,
        flow: LangflowFlow,
        conversation=None,
        session_id: Optional[str] = None
    ) -> LangflowSession:
        """Get or create a Langflow session."""
        if session_id:
            try:
                return LangflowSession.objects.get(session_id=session_id)
            except LangflowSession.DoesNotExist:
                pass
        
        if conversation:
            try:
                return LangflowSession.objects.get(
                    flow=flow,
                    conversation=conversation
                )
            except LangflowSession.DoesNotExist:
                pass
        
        session = LangflowSession.objects.create(
            flow=flow,
            conversation=conversation,
            session_id=session_id or str(uuid.uuid4()),
            context=flow.default_context.copy()
        )
        
        logger.info(f"New Langflow session created: {session.session_id}")
        return session

    def process_message(
        self,
        flow_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        conversation=None
    ) -> Dict[str, Any]:
        """Process a message through Langflow."""
        flow = self.get_flow(flow_id)
        
        if flow.status != LangflowFlow.FlowStatus.ACTIVE:
            logger.warning(f"Flow {flow_id} is not active")
            return {'response': None, 'error': 'Flow is not active'}
        
        session = self.get_or_create_session(flow, conversation, session_id)
        
        session.add_to_history('user', message)
        
        merged_context = {**session.context, **(context or {})}
        
        start_time = time.time()
        
        try:
            response = self._run_flow(
                flow=flow,
                message=message,
                session=session,
                context=merged_context
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            output_message = self._extract_response(response)
            
            session.add_to_history('assistant', output_message)
            
            self._log_interaction(
                flow=flow,
                session=session,
                input_message=message,
                output_message=output_message,
                status=LangflowLog.LogStatus.SUCCESS,
                request_payload={'message': message, 'context': merged_context},
                response_payload=response,
                duration_ms=duration_ms
            )
            
            logger.info(f"Message processed by Langflow: {flow.name}")
            
            return {
                'response': output_message,
                'session_id': session.session_id,
                'flow_id': str(flow.id),
                'raw_response': response
            }
            
        except LangflowAPIError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            self._log_interaction(
                flow=flow,
                session=session,
                input_message=message,
                output_message='',
                status=LangflowLog.LogStatus.ERROR,
                request_payload={'message': message, 'context': merged_context},
                response_payload={},
                duration_ms=duration_ms,
                error_message=str(e)
            )
            
            raise

    def _run_flow(
        self,
        flow: LangflowFlow,
        message: str,
        session: LangflowSession,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run the Langflow flow."""
        endpoint = flow.endpoint_url or f"api/v1/run/{flow.flow_id}"
        
        if endpoint.startswith('http'):
            url = endpoint
        else:
            url = f"{self.base_url}/{endpoint}"
        
        payload = {
            'input_value': message,
            'output_type': flow.output_type,
            'input_type': flow.input_type,
            'tweaks': flow.tweaks,
            'session_id': session.session_id,
        }
        
        if context:
            payload['tweaks']['context'] = context
        
        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=flow.timeout_seconds
            )
            
            response_data = response.json() if response.content else {}
            
            if response.status_code >= 400:
                raise LangflowAPIError(
                    message=response_data.get('detail', 'Langflow API error'),
                    code=str(response.status_code),
                    details=response_data
                )
            
            return response_data
            
        except requests.exceptions.Timeout:
            raise LangflowAPIError(
                message="Langflow API timeout",
                code='timeout'
            )
        except requests.exceptions.RequestException as e:
            raise LangflowAPIError(
                message=f"Request failed: {str(e)}",
                code='request_failed'
            )

    def _extract_response(self, response: Dict[str, Any]) -> str:
        """Extract the response text from Langflow response."""
        if 'outputs' in response:
            outputs = response['outputs']
            if isinstance(outputs, list) and outputs:
                first_output = outputs[0]
                if 'outputs' in first_output:
                    inner_outputs = first_output['outputs']
                    if isinstance(inner_outputs, list) and inner_outputs:
                        result = inner_outputs[0].get('results', {})
                        if 'message' in result:
                            message = result['message']
                            if isinstance(message, dict):
                                return message.get('text', str(message))
                            return str(message)
        
        if 'result' in response:
            return str(response['result'])
        
        if 'output' in response:
            return str(response['output'])
        
        if 'message' in response:
            return str(response['message'])
        
        if 'text' in response:
            return str(response['text'])
        
        return str(response)

    def _log_interaction(
        self,
        flow: LangflowFlow,
        session: LangflowSession,
        input_message: str,
        output_message: str,
        status: str,
        request_payload: Dict,
        response_payload: Dict,
        duration_ms: int,
        error_message: str = ''
    ):
        """Log a Langflow interaction."""
        LangflowLog.objects.create(
            flow=flow,
            session=session,
            input_message=input_message,
            output_message=output_message,
            status=status,
            request_payload=request_payload,
            response_payload=response_payload,
            duration_ms=duration_ms,
            error_message=error_message
        )

    def update_session_context(
        self,
        session_id: str,
        context: Dict[str, Any]
    ) -> LangflowSession:
        """Update session context."""
        try:
            session = LangflowSession.objects.get(session_id=session_id)
        except LangflowSession.DoesNotExist:
            raise NotFoundError(message="Session not found")
        
        session.context.update(context)
        session.save(update_fields=['context', 'updated_at'])
        
        return session

    def clear_session_history(self, session_id: str) -> LangflowSession:
        """Clear session history."""
        try:
            session = LangflowSession.objects.get(session_id=session_id)
        except LangflowSession.DoesNotExist:
            raise NotFoundError(message="Session not found")
        
        session.history = []
        session.save(update_fields=['history', 'updated_at'])
        
        return session

    def get_session_history(self, session_id: str) -> List[Dict[str, str]]:
        """Get session history."""
        try:
            session = LangflowSession.objects.get(session_id=session_id)
        except LangflowSession.DoesNotExist:
            raise NotFoundError(message="Session not found")
        
        return session.history

    def list_flows(self, account_id: Optional[str] = None) -> List[LangflowFlow]:
        """List available flows."""
        queryset = LangflowFlow.objects.filter(
            is_active=True,
            status=LangflowFlow.FlowStatus.ACTIVE
        )
        
        if account_id:
            queryset = queryset.filter(accounts__id=account_id)
        
        return list(queryset)

    def get_flow_stats(self, flow_id: str) -> Dict[str, Any]:
        """Get flow statistics."""
        flow = self.get_flow(flow_id)
        
        from django.db.models import Count, Avg
        
        logs = LangflowLog.objects.filter(flow=flow)
        
        stats = logs.aggregate(
            total_interactions=Count('id'),
            avg_duration=Avg('duration_ms')
        )
        
        status_counts = logs.values('status').annotate(count=Count('id'))
        
        return {
            'flow_id': str(flow.id),
            'flow_name': flow.name,
            'total_interactions': stats['total_interactions'] or 0,
            'avg_duration_ms': round(stats['avg_duration'] or 0, 2),
            'by_status': {s['status']: s['count'] for s in status_counts},
            'active_sessions': LangflowSession.objects.filter(flow=flow).count(),
        }
