import React, { useEffect, useState } from 'react';
import logger from '../../services/logger';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Input, Select, PageLoading, PageTitle } from '../../components/common';
import { whatsappService, agentsService, getErrorMessage } from '../../services';
import { useAccountStore } from '../../stores/accountStore';
import { WhatsAppAccount } from '../../types';
import { Agent } from '../../services/agents';

export const AccountFormPage: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const { updateAccount } = useAccountStore();
  const isEditing = !!id;

  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [formData, setFormData] = useState({
    name: '',
    phone_number_id: '',
    waba_id: '',
    phone_number: '',
    display_phone_number: '',
    access_token: '',
    webhook_verify_token: '',
    auto_response_enabled: true,
    human_handoff_enabled: true,
    default_agent: '',
  });

  useEffect(() => {
    loadAgents();
    if (isEditing) {
      loadAccount();
    }
  }, [id]);

  const loadAgents = async () => {
    try {
      const agents = await agentsService.getAgents();
      setAgents(agents.filter((a: Agent) => a.status === 'active'));
    } catch (error) {
      logger.error('Error loading agents:', error);
    }
  };

  const loadAccount = async () => {
    setIsLoading(true);
    try {
      const account = await whatsappService.getAccount(id!);
      setFormData({
        name: account.name,
        phone_number_id: account.phone_number_id,
        waba_id: account.waba_id,
        phone_number: account.phone_number,
        display_phone_number: account.display_phone_number,
        access_token: '',
        webhook_verify_token: '',
        auto_response_enabled: account.auto_response_enabled,
        human_handoff_enabled: account.human_handoff_enabled,
        default_agent: account.default_agent || '',
      });
    } catch (error) {
      toast.error(getErrorMessage(error));
      navigate('/accounts');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);

    try {
      const data: Record<string, unknown> = {
        name: formData.name,
        display_phone_number: formData.display_phone_number,
        auto_response_enabled: formData.auto_response_enabled,
        human_handoff_enabled: formData.human_handoff_enabled,
        default_agent: formData.default_agent || null,
      };

      if (!isEditing) {
        data.phone_number_id = formData.phone_number_id;
        data.waba_id = formData.waba_id;
        data.phone_number = formData.phone_number;
        data.access_token = formData.access_token;
        data.webhook_verify_token = formData.webhook_verify_token;
      } else if (formData.access_token) {
        data.access_token = formData.access_token;
      }

      let account: WhatsAppAccount;
      if (isEditing) {
        account = await whatsappService.updateAccount(id!, data);
        updateAccount(account);
        toast.success('Conta atualizada com sucesso!');
      } else {
        account = await whatsappService.createAccount(data as any);
        toast.success('Conta criada com sucesso!');
      }

      navigate('/accounts');
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return <PageLoading />;
  }

  return (
    <div className="p-6">
      <PageTitle
        title={isEditing ? 'Editar Conta' : 'Nova Conta'}
        subtitle={isEditing ? formData.name : 'Cadastre uma nova conta WhatsApp Business'}
        actions={
          <Button variant="ghost" onClick={() => navigate('/accounts')} leftIcon={<ArrowLeftIcon className="w-5 h-5" />}>
            Voltar
          </Button>
        }
      />

      <form onSubmit={handleSubmit}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Basic Info */}
            <Card title="Informações Básicas">
              <div className="space-y-4">
                <Input
                  label="Nome da Conta"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Ex: Minha Empresa"
                />
                <Input
                  label="Phone Number ID"
                  required
                  disabled={isEditing}
                  value={formData.phone_number_id}
                  onChange={(e) => setFormData({ ...formData, phone_number_id: e.target.value })}
                  placeholder="ID do número no Meta"
                  helperText="Encontre no Meta Developer Portal"
                />
                <Input
                  label="WABA ID"
                  required
                  disabled={isEditing}
                  value={formData.waba_id}
                  onChange={(e) => setFormData({ ...formData, waba_id: e.target.value })}
                  placeholder="WhatsApp Business Account ID"
                />
                <Input
                  label="Número de Telefone"
                  required
                  disabled={isEditing}
                  value={formData.phone_number}
                  onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                  placeholder="5511999999999"
                />
                <Input
                  label="Número para Exibição"
                  value={formData.display_phone_number}
                  onChange={(e) => setFormData({ ...formData, display_phone_number: e.target.value })}
                  placeholder="+55 11 99999-9999"
                />
              </div>
            </Card>

            {/* Authentication */}
            <Card title="Autenticação">
              <div className="space-y-4">
                <Input
                  label="Access Token"
                  type="password"
                  required={!isEditing}
                  value={formData.access_token}
                  onChange={(e) => setFormData({ ...formData, access_token: e.target.value })}
                  placeholder={isEditing ? 'Deixe em branco para manter o atual' : 'Token de acesso do Meta'}
                  helperText={isEditing ? 'Preencha apenas se quiser atualizar o token' : 'Token permanente ou de longa duração'}
                />
                <Input
                  label="Webhook Verify Token"
                  value={formData.webhook_verify_token}
                  onChange={(e) => setFormData({ ...formData, webhook_verify_token: e.target.value })}
                  placeholder="Token de verificação do webhook"
                  helperText="Usado para verificar webhooks do Meta"
                />
              </div>
            </Card>

            {/* Automation */}
            <Card title="Automação">
              <div className="space-y-4">
                <Select
                  label="Agente IA Padrão"
                  value={formData.default_agent}
                  onChange={(e) => setFormData({ ...formData, default_agent: e.target.value })}
                  options={[
                    { value: '', label: 'Nenhum' },
                    ...agents.map((agent) => ({ value: agent.id, label: agent.name })),
                  ]}
                />
                <p className="text-xs text-gray-500 dark:text-zinc-400">
                  <Link to="/agents" className="text-green-600 hover:text-green-700">Gerenciar Agentes IA →</Link>
                </p>
                <div className="flex items-center justify-between py-2">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Resposta Automática</p>
                    <p className="text-sm text-gray-500 dark:text-zinc-400">Processar mensagens com Agente IA automaticamente</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.auto_response_enabled}
                      onChange={(e) => setFormData({ ...formData, auto_response_enabled: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white dark:bg-zinc-900 after:border-gray-300 dark:border-zinc-700 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
                  </label>
                </div>
                <div className="flex items-center justify-between py-2">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">Handoff para Humano</p>
                    <p className="text-sm text-gray-500 dark:text-zinc-400">Permitir transferência para atendente humano</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.human_handoff_enabled}
                      onChange={(e) => setFormData({ ...formData, human_handoff_enabled: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white dark:bg-zinc-900 after:border-gray-300 dark:border-zinc-700 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
                  </label>
                </div>
              </div>
            </Card>

            {/* Actions */}
            <Card>
              <div className="flex justify-end gap-3">
                <Button variant="secondary" onClick={() => navigate('/accounts')}>
                  Cancelar
                </Button>
                <Button type="submit" isLoading={isSaving}>
                  {isEditing ? 'Salvar Alterações' : 'Criar Conta'}
                </Button>
              </div>
            </Card>
          </div>
        </form>
    </div>
  );
};
