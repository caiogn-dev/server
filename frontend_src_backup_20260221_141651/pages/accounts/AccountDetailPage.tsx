import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  KeyIcon,
  CheckCircleIcon,
  XCircleIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import toast from 'react-hot-toast';
import { Card, Button, StatusBadge, Modal, Input, PageLoading, StatCard, PageTitle } from '../../components/common';
import { whatsappService, getErrorMessage } from '../../services';
import { WhatsAppAccount, MessageTemplate } from '../../types';

export const AccountDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [account, setAccount] = useState<WhatsAppAccount | null>(null);
  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [businessProfile, setBusinessProfile] = useState<Record<string, unknown> | null>(null);
  const [messageStats, setMessageStats] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Modals
  const [rotateTokenModal, setRotateTokenModal] = useState(false);
  const [newToken, setNewToken] = useState('');

  useEffect(() => {
    if (id) {
      loadAccount();
    }
  }, [id]);

  const loadAccount = async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const accountData = await whatsappService.getAccount(id);
      setAccount(accountData);

      // Load templates
      const templatesResponse = await whatsappService.getTemplates(id);
      setTemplates(templatesResponse.results);

      // Load business profile
      try {
        const profile = await whatsappService.getBusinessProfile(id);
        setBusinessProfile(profile);
      } catch {
        // Profile might not be available
      }

      // Load message stats for last 30 days
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 30);
      try {
        const stats = await whatsappService.getMessageStats(
          id,
          startDate.toISOString().split('T')[0],
          endDate.toISOString().split('T')[0]
        );
        setMessageStats(stats);
      } catch {
        // Stats might not be available
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
      navigate('/accounts');
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleStatus = async () => {
    if (!account) return;
    setActionLoading('status');
    try {
      const updated = account.status === 'active'
        ? await whatsappService.deactivateAccount(account.id)
        : await whatsappService.activateAccount(account.id);
      setAccount(updated);
      toast.success(`Conta ${updated.status === 'active' ? 'ativada' : 'desativada'} com sucesso!`);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setActionLoading(null);
    }
  };

  const handleSyncTemplates = async () => {
    if (!account) return;
    setActionLoading('sync');
    try {
      const result = await whatsappService.syncTemplates(account.id);
      toast.success(result.message);
      loadAccount();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setActionLoading(null);
    }
  };

  const handleRotateToken = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!account || !newToken) return;
    setActionLoading('rotate');
    try {
      const result = await whatsappService.rotateToken(account.id, newToken);
      toast.success(result.message);
      setRotateTokenModal(false);
      setNewToken('');
      loadAccount();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setActionLoading(null);
    }
  };

  if (isLoading || !account) {
    return <PageLoading />;
  }

  return (
    <div className="p-6 space-y-6">
      <PageTitle
        title={account.name}
        subtitle={account.display_phone_number || account.phone_number}
        actions={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              leftIcon={<ArrowLeftIcon className="w-5 h-5" />}
              onClick={() => navigate('/accounts')}
            >
              Voltar
            </Button>
            <Button
              variant="secondary"
              onClick={() => navigate(`/accounts/${account.id}/edit`)}
            >
              Editar
            </Button>
          </div>
        }
      />

        {/* Status and Actions */}
        <Card>
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div className="flex items-center gap-4">
              <StatusBadge status={account.status} />
              <span className="text-sm text-gray-500 dark:text-zinc-400">
                Token v{account.token_version}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant={account.status === 'active' ? 'secondary' : 'primary'}
                size="sm"
                isLoading={actionLoading === 'status'}
                onClick={handleToggleStatus}
              >
                {account.status === 'active' ? 'Desativar' : 'Ativar'}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<ArrowPathIcon className="w-4 h-4" />}
                isLoading={actionLoading === 'sync'}
                onClick={handleSyncTemplates}
              >
                Sincronizar Templates
              </Button>
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<KeyIcon className="w-4 h-4" />}
                onClick={() => setRotateTokenModal(true)}
              >
                Rotacionar Token
              </Button>
            </div>
          </div>
        </Card>

        {/* Stats */}
        {messageStats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <StatCard
              title="Mensagens Enviadas"
              value={(messageStats as Record<string, number>).sent || 0}
              icon={<ChartBarIcon className="w-6 h-6" />}
            />
            <StatCard
              title="Mensagens Entregues"
              value={(messageStats as Record<string, number>).delivered || 0}
              icon={<CheckCircleIcon className="w-6 h-6" />}
            />
            <StatCard
              title="Mensagens Lidas"
              value={(messageStats as Record<string, number>).read || 0}
              icon={<CheckCircleIcon className="w-6 h-6" />}
            />
            <StatCard
              title="Mensagens Falhas"
              value={(messageStats as Record<string, number>).failed || 0}
              icon={<XCircleIcon className="w-6 h-6" />}
            />
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Account Details */}
          <Card title="Detalhes da Conta">
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Phone Number ID</p>
                  <p className="font-mono text-sm">{account.phone_number_id}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">WABA ID</p>
                  <p className="font-mono text-sm">{account.waba_id}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Resposta Automática</p>
                  <p className={account.auto_response_enabled ? 'text-green-600' : 'text-gray-400'}>
                    {account.auto_response_enabled ? 'Ativada' : 'Desativada'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Handoff Humano</p>
                  <p className={account.human_handoff_enabled ? 'text-green-600' : 'text-gray-400'}>
                    {account.human_handoff_enabled ? 'Ativado' : 'Desativado'}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Criado em</p>
                  <p>{format(new Date(account.created_at), "dd/MM/yyyy HH:mm", { locale: ptBR })}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Atualizado em</p>
                  <p>{format(new Date(account.updated_at), "dd/MM/yyyy HH:mm", { locale: ptBR })}</p>
                </div>
              </div>
              {account.default_agent && (
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Agente IA Padrão</p>
                  <p className="font-medium">{account.default_agent_name || account.default_agent}</p>
                </div>
              )}
            </div>
          </Card>

          {/* Business Profile */}
          <Card title="Perfil do Negócio">
            {businessProfile ? (
              <div className="space-y-4">
                {(businessProfile as Record<string, string>).about && (
                  <div>
                    <p className="text-sm text-gray-500 dark:text-zinc-400">Sobre</p>
                    <p>{(businessProfile as Record<string, string>).about}</p>
                  </div>
                )}
                {(businessProfile as Record<string, string>).address && (
                  <div>
                    <p className="text-sm text-gray-500 dark:text-zinc-400">Endereço</p>
                    <p>{(businessProfile as Record<string, string>).address}</p>
                  </div>
                )}
                {(businessProfile as Record<string, string>).email && (
                  <div>
                    <p className="text-sm text-gray-500 dark:text-zinc-400">Email</p>
                    <p>{(businessProfile as Record<string, string>).email}</p>
                  </div>
                )}
                {(businessProfile as Record<string, string>).websites && (
                  <div>
                    <p className="text-sm text-gray-500 dark:text-zinc-400">Websites</p>
                    <p>{(businessProfile as Record<string, string>).websites}</p>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-gray-500 dark:text-zinc-400">Perfil não disponível</p>
            )}
          </Card>
        </div>

        {/* Templates */}
        <Card title={`Templates de Mensagem (${templates.length})`}>
          {templates.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead>
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">
                      Nome
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">
                      Idioma
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">
                      Categoria
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {templates.map((template) => (
                    <tr key={template.id}>
                      <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                        {template.name}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-zinc-400">
                        {template.language}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-zinc-400">
                        {template.category}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={template.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-gray-500 dark:text-zinc-400 text-center py-8">
              Nenhum template encontrado. Clique em "Sincronizar Templates" para importar.
            </p>
          )}
        </Card>

        {/* Metadata */}
        {account.metadata && Object.keys(account.metadata).length > 0 && (
          <Card title="Metadados">
            <pre className="bg-gray-50 dark:bg-black p-4 rounded-lg overflow-x-auto text-sm">
              {JSON.stringify(account.metadata, null, 2)}
            </pre>
          </Card>
        )}

      {/* Rotate Token Modal */}
      <Modal
        isOpen={rotateTokenModal}
        onClose={() => setRotateTokenModal(false)}
        title="Rotacionar Token de Acesso"
        size="sm"
      >
        <form onSubmit={handleRotateToken} className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-zinc-400">
            Insira o novo token de acesso do WhatsApp Business API. O token atual será substituído.
          </p>
          <Input
            label="Novo Token de Acesso"
            type="password"
            required
            value={newToken}
            onChange={(e) => setNewToken(e.target.value)}
            placeholder="EAAxxxxxxx..."
          />
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setRotateTokenModal(false)}>
              Cancelar
            </Button>
            <Button type="submit" isLoading={actionLoading === 'rotate'}>
              Rotacionar Token
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
