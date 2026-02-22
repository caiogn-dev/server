import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { AgentForm } from '../../components/agents';
import agentsService, { CreateAgentData } from '../../services/agents';
import { whatsappService } from '../../services';

interface WhatsAppAccount {
  id: string;
  name: string;
  phone_number: string;
}

export const AgentCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);
  const [whatsappAccounts, setWhatsappAccounts] = useState<WhatsAppAccount[]>([]);

  useEffect(() => {
    const loadAccounts = async () => {
      try {
        const response = await whatsappService.getAccounts();
        setWhatsappAccounts(response.results || []);
      } catch (error) {
        console.error('Erro ao carregar contas WhatsApp:', error);
      }
    };
    loadAccounts();
  }, []);

  const handleSubmit = async (data: CreateAgentData) => {
    setIsLoading(true);
    try {
      const newAgent = await agentsService.createAgent(data);
      navigate(`/agents/${newAgent.id}`);
    } catch (error) {
      console.error('Erro ao criar agente:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/agents')}
          className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <ArrowLeftIcon className="w-5 h-5 text-zinc-500" />
        </button>
        
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
            Criar Novo Agente
          </h1>
          <p className="text-zinc-500 dark:text-zinc-400">
            Configure um novo agente de inteligência artificial
          </p>
        </div>
      </div>

      {/* Form */}
      <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
        <AgentForm
          whatsappAccounts={whatsappAccounts}
          onSubmit={handleSubmit}
          onCancel={() => navigate('/agents')}
          isLoading={isLoading}
        />
      </div>
    </div>
  );
};

export default AgentCreatePage;
