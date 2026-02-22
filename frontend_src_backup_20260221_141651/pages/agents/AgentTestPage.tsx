import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { AgentChatTest } from '../../components/agents';
import agentsService, { AgentDetail } from '../../services/agents';

export const AgentTestPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadAgent = useCallback(async () => {
    if (!id) return;
    
    setIsLoading(true);
    try {
      const agentData = await agentsService.getAgent(id);
      setAgent(agentData);
    } catch (error) {
      console.error('Erro ao carregar agente:', error);
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadAgent();
  }, [loadAgent]);

  const handleSendMessage = async (message: string, sessionId?: string) => {
    if (!id) throw new Error('ID do agente não encontrado');
    
    return await agentsService.processMessage(id, {
      message,
      session_id: sessionId,
      context: { test: true },
    });
  };

  if (isLoading) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="animate-pulse">
          <div className="h-8 w-64 bg-zinc-200 dark:bg-zinc-700 rounded mb-4" />
          <div className="h-[600px] bg-zinc-200 dark:bg-zinc-700 rounded-xl" />
        </div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="text-center py-16">
          <p className="text-xl font-medium text-zinc-900 dark:text-white mb-2">
            Agente não encontrado
          </p>
          <button
            onClick={() => navigate('/agents')}
            className="text-primary-600 hover:text-primary-700"
          >
            Voltar para lista
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate(`/agents/${id}`)}
          className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5 text-zinc-500" />
        </button>
        
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
            Testar: {agent.name}
          </h1>
          <p className="text-zinc-500 dark:text-zinc-400">
            {agent.provider} / {agent.model_name}
          </p>
        </div>
      </div>

      {/* Chat Test */}
      <AgentChatTest
        agentName={agent.name}
        onSendMessage={handleSendMessage}
        onClearChat={() => {}}
      />
    </div>
  );
};

export default AgentTestPage;
