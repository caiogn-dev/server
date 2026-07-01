"""
Flow Executor Service

Executa fluxos do Flow Builder (React Flow).
Versão POC: Suporta fluxo linear simples.
"""
from typing import Dict, Any, Optional
import time
import logging

logger = logging.getLogger(__name__)


class FlowExecutor:
    """
    Executa fluxos de conversação baseados no JSON do React Flow.
    
    Versão POC:
    - Suporta nós: start, message, end
    - Fluxo linear (sem condições complexas)
    - Contexto básico
    """
    
    def __init__(self, flow, conversation):
        """
        Args:
            flow: Instância de AgentFlow
            conversation: Instância de Conversation
        """
        self.flow = flow
        self.conversation = conversation
        self.session = self._get_or_create_session()
    
    def process_message(self, message_text: str) -> Dict[str, Any]:
        """
        Processa uma mensagem do usuário no contexto do fluxo.
        
        Args:
            message_text: Mensagem recebida do usuário
            
        Returns:
            Dict com tipo e conteúdo da resposta
        """
        start_time = time.time()
        
        try:
            flow_data = self.flow.flow_json
            nodes = {n['id']: n for n in flow_data.get('nodes', [])}
            edges = flow_data.get('edges', [])
            
            if not nodes:
                return {'type': 'error', 'content': 'Fluxo vazio'}
            
            # Se está esperando input, processa ele
            if self.session.is_waiting_input:
                result = self._process_input(message_text, nodes, edges)
                self._log_execution('input', message_text, result, start_time)
                return result
            
            # Se não tem nó atual, começa do início
            if not self.session.current_node_id:
                current_node = self._find_start_node(nodes)
                if not current_node:
                    return {'type': 'error', 'content': 'Fluxo sem nó inicial'}
            else:
                current_node = nodes.get(self.session.current_node_id)
                if not current_node:
                    return {'type': 'error', 'content': 'Nó atual não encontrado'}
            
            # Executa nó atual
            result = self._execute_node(current_node)
            
            # Navega para próximo nó
            next_node_id = self._find_next_node(current_node['id'], edges)
            if next_node_id:
                self.session.current_node_id = next_node_id
                self.session.node_history.append(next_node_id)
                self.session.save()
                
                # Se próximo nó é message/end, executa automaticamente
                next_node = nodes.get(next_node_id)
                if next_node and next_node.get('type') in ['message', 'end']:
                    result = self._execute_node(next_node)
            
            self._log_execution(current_node.get('type', 'unknown'), message_text, result, start_time)
            return result
            
        except Exception as e:
            logger.error(f"[FlowExecutor] Erro: {e}", exc_info=True)
            return {'type': 'error', 'content': 'Erro ao processar mensagem'}
    
    def _execute_node(self, node: Dict) -> Dict[str, Any]:
        """
        Executa um nó baseado no seu tipo.
        
        Args:
            node: Dicionário com dados do nó
            
        Returns:
            Resultado da execução do nó
        """
        node_type = node.get('type')
        data = node.get('data', {})
        
        processors = {
            'start': self._process_start,
            'message': self._process_message,
            'end': self._process_end,
        }
        
        processor = processors.get(node_type)
        if not processor:
            logger.warning(f"[FlowExecutor] Tipo de nó desconhecido: {node_type}")
            return {'type': 'error', 'content': f'Tipo de nó não suportado: {node_type}'}
        
        return processor(data)
    
    def _process_start(self, data: Dict) -> Dict[str, Any]:
        """Processa nó de início - apenas continua."""
        return {'type': 'continue', 'content': ''}
    
    def _process_message(self, data: Dict) -> Dict[str, Any]:
        """
        Processa nó de mensagem.
        
        Renderiza template com contexto e retorna mensagem.
        """
        content = data.get('content', '')
        buttons = data.get('buttons', [])
        
        # Renderiza variáveis do contexto
        content = self._render_template(content)
        
        # Se tem botões, marca que está esperando escolha
        if buttons:
            self.session.is_waiting_input = True
            self.session.input_type_expected = 'button'
            self.session.save()
        
        return {
            'type': 'message',
            'content': content,
            'buttons': buttons,
        }
    
    def _process_end(self, data: Dict) -> Dict[str, Any]:
        """Processa nó de fim - finaliza sessão."""
        content = data.get('content', 'Obrigado pelo contato! 🙏')
        content = self._render_template(content)
        
        # Limpa sessão
        self.session.reset()
        
        return {
            'type': 'end',
            'content': content,
        }
    
    def _process_input(self, message_text: str, nodes: Dict, edges: list) -> Dict[str, Any]:
        """
        Processa input do usuário quando esperando.
        """
        input_type = self.session.input_type_expected
        
        # Valida input
        if input_type == 'number':
            if not message_text.isdigit():
                return {
                    'type': 'message',
                    'content': 'Por favor, digite apenas números.',
                }
            # Salva no contexto
            self.session.update_context('quantity', int(message_text))
        
        elif input_type == 'button':
            # Salva escolha do botão
            self.session.update_context('button_choice', message_text)
        
        else:
            # Texto genérico
            self.session.update_context('last_input', message_text)
        
        # Limpa flag de espera
        self.session.is_waiting_input = False
        self.session.input_type_expected = ''
        self.session.save()
        
        # Continua fluxo
        current_node = nodes.get(self.session.current_node_id)
        if current_node:
            next_node_id = self._find_next_node(current_node['id'], edges)
            if next_node_id:
                self.session.current_node_id = next_node_id
                self.session.save()
                
                next_node = nodes.get(next_node_id)
                if next_node:
                    return self._execute_node(next_node)
        
        return {'type': 'continue', 'content': ''}
    
    def _render_template(self, template: str) -> str:
        """
        Substitui {{variaveis}} pelo contexto.
        
        Args:
            template: String com possíveis {{variaveis}}
            
        Returns:
            String renderizada
        """
        if not template:
            return ''
        
        result = template
        for key, value in self.session.context.items():
            placeholder = f'{{{{{key}}}}}'
            result = result.replace(placeholder, str(value))
        
        return result
    
    def _find_start_node(self, nodes: Dict) -> Optional[Dict]:
        """Encontra nó do tipo 'start' ou retorna primeiro nó."""
        for node in nodes.values():
            if node.get('type') == 'start':
                return node
        return list(nodes.values())[0] if nodes else None
    
    def _find_next_node(self, current_id: str, edges: list) -> Optional[str]:
        """Encontra próximo nó baseado nas edges."""
        for edge in edges:
            if edge.get('source') == current_id:
                return edge.get('target')
        return None
    
    def _get_or_create_session(self):
        """Pega ou cria sessão do fluxo."""
        from apps.automation.models import FlowSession
        
        session, created = FlowSession.objects.get_or_create(
            conversation=self.conversation,
            defaults={
                'flow': self.flow,
                'context': {},
                'node_history': [],
            }
        )
        
        # Se mudou de fluxo, reseta
        if session.flow_id != self.flow.id:
            session.flow = self.flow
            session.reset()
        
        return session
    
    def _log_execution(self, node_type: str, input_msg: str, result: Dict, start_time: float):
        """Registra log de execução."""
        from apps.automation.models import FlowExecutionLog
        
        execution_time = int((time.time() - start_time) * 1000)
        
        try:
            FlowExecutionLog.objects.create(
                session=self.session,
                flow=self.flow,
                node_id=self.session.current_node_id or 'unknown',
                node_type=node_type,
                input_message=input_msg,
                output_message=result.get('content', ''),
                context_snapshot=self.session.context,
                execution_time_ms=execution_time,
                success=result.get('type') != 'error',
                error_message=result.get('content', '') if result.get('type') == 'error' else '',
            )
            # Em evento terminal (fim do fluxo ou erro), atualiza os contadores do
            # fluxo (eram sempre 0 no painel). Só aqui p/ não recalcular a cada nó.
            if result.get('type') in ('end', 'error'):
                self.flow.refresh_execution_stats()
        except Exception as e:
            logger.error(f"[FlowExecutor] Erro ao logar: {e}")
