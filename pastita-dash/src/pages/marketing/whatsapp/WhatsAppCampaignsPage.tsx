/**
 * WhatsApp Campaigns List Page
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  DevicePhoneMobileIcon,
  PlusIcon,
  PlayIcon,
  PauseIcon,
  StopIcon,
  ChartBarIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Loading, Badge } from '../../../components/common';
import { whatsappService } from '../../../services/whatsapp';
import { campaignsService, Campaign } from '../../../services/campaigns';
import logger from '../../../services/logger';

// Local type definitions
type CampaignStats = {
  id: string;
  name: string;
  status: string;
  total_recipients: number;
  messages_sent: number;
  messages_delivered: number;
  messages_read: number;
  messages_failed: number;
  delivery_rate: number;
  read_rate: number;
  pending: number;
  started_at: string | null;
  completed_at: string | null;
};

// =============================================================================
// COMPONENT
// =============================================================================

export const WhatsAppCampaignsPage: React.FC = () => {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);
  const [stats, setStats] = useState<CampaignStats | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // =============================================================================
  // DATA LOADING
  // =============================================================================

  const loadCampaigns = useCallback(async () => {
    try {
      setLoading(true);
      const response = await campaignsService.getCampaigns();
      setCampaigns(response.results || []);
    } catch (error) {
      logger.error('Failed to load campaigns', error);
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCampaigns();
  }, [loadCampaigns]);

  const loadStats = async (campaignId: string) => {
    try {
      const statsData = await campaignsService.getCampaignStats(campaignId);
      setStats(statsData as CampaignStats);
    } catch (error) {
      logger.error('Failed to load stats', error);
    }
  };

  // =============================================================================
  // HANDLERS
  // =============================================================================

  const handleStartCampaign = async (campaign: Campaign) => {
    setActionLoading(campaign.id);
    try {
      await campaignsService.startCampaign(campaign.id);
      toast.success('Campanha iniciada!');
      loadCampaigns();
    } catch (error) {
      logger.error('Failed to start campaign', error);
      toast.error('Erro ao iniciar campanha');
    } finally {
      setActionLoading(null);
    }
  };

  const handlePauseCampaign = async (campaign: Campaign) => {
    setActionLoading(campaign.id);
    try {
      await campaignsService.pauseCampaign(campaign.id);
      toast.success('Campanha pausada');
      loadCampaigns();
    } catch (error) {
      logger.error('Failed to pause campaign', error);
      toast.error('Erro ao pausar campanha');
    } finally {
      setActionLoading(null);
    }
  };

  const handleResumeCampaign = async (campaign: Campaign) => {
    setActionLoading(campaign.id);
    try {
      await campaignsService.resumeCampaign(campaign.id);
      toast.success('Campanha retomada!');
      loadCampaigns();
    } catch (error) {
      logger.error('Failed to resume campaign', error);
      toast.error('Erro ao retomar campanha');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancelCampaign = async (campaign: Campaign) => {
    if (!confirm('Tem certeza que deseja cancelar esta campanha?')) return;
    
    setActionLoading(campaign.id);
    try {
      await campaignsService.cancelCampaign(campaign.id);
      toast.success('Campanha cancelada');
      loadCampaigns();
    } catch (error) {
      logger.error('Failed to cancel campaign', error);
      toast.error('Erro ao cancelar campanha');
    } finally {
      setActionLoading(null);
    }
  };

  const handleForceProcess = async (campaign: Campaign) => {
    setActionLoading(campaign.id);
    try {
      // Process campaign by triggering a batch via getRecipients
      const recipients = await campaignsService.getCampaignRecipients(campaign.id, 'pending');
      toast.success(`Processando: ${recipients.length} pendentes`);
      loadCampaigns();
      if (selectedCampaign?.id === campaign.id) {
        await loadStats(campaign.id);
      }
    } catch (error) {
      logger.error('Failed to process campaign', error);
      toast.error('Erro ao processar campanha');
    } finally {
      setActionLoading(null);
    }
  };

  const handleViewStats = async (campaign: Campaign) => {
    setSelectedCampaign(campaign);
    await loadStats(campaign.id);
  };

  // =============================================================================
  // HELPERS
  // =============================================================================

  const getStatusBadge = (status: string) => {
    const statusConfig: Record<string, { className: string; label: string; icon: React.ReactNode }> = {
      draft: { 
        className: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-zinc-300', 
        label: 'Rascunho', 
        icon: null 
      },
      scheduled: { 
        className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300', 
        label: 'Agendada', 
        icon: <ClockIcon className="w-3 h-3" /> 
      },
      running: { 
        className: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300', 
        label: 'Enviando', 
        icon: <ArrowPathIcon className="w-3 h-3 animate-spin" /> 
      },
      paused: { 
        className: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300', 
        label: 'Pausada', 
        icon: <PauseIcon className="w-3 h-3" /> 
      },
      completed: { 
        className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300', 
        label: 'Concluída', 
        icon: <CheckCircleIcon className="w-3 h-3" /> 
      },
      cancelled: { 
        className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300', 
        label: 'Cancelada', 
        icon: <XCircleIcon className="w-3 h-3" /> 
      },
    };

    const config = statusConfig[status] || { 
      className: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-zinc-300', 
      label: status, 
      icon: null 
    };

    return (
      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.className}`}>
        {config.icon}
        {config.label}
      </span>
    );
  };

  // =============================================================================
  // RENDER
  // =============================================================================

  if (loading) {
    return <Loading />;
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Campanhas WhatsApp</h1>
          <p className="text-gray-500 dark:text-zinc-400">
            Gerencie suas campanhas de mensagens em massa
          </p>
        </div>
        <Button onClick={() => navigate('/marketing/whatsapp/new')}>
          <PlusIcon className="w-5 h-5 mr-2" />
          Nova Campanha
        </Button>
      </div>

      {/* Campaigns List */}
      {campaigns.length === 0 ? (
        <Card className="p-12 text-center">
          <DevicePhoneMobileIcon className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            Nenhuma campanha criada
          </h2>
          <p className="text-gray-500 dark:text-zinc-400 mb-6">
            Crie sua primeira campanha de WhatsApp para alcançar seus clientes
          </p>
          <Button onClick={() => navigate('/marketing/whatsapp/new')}>
            <PlusIcon className="w-5 h-5 mr-2" />
            Criar Campanha
          </Button>
        </Card>
      ) : (
        <div className="space-y-4">
          {campaigns.map((campaign) => (
            <Card key={campaign.id} className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                      {campaign.name}
                    </h3>
                    {getStatusBadge(campaign.status)}
                  </div>
                  
                  <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-zinc-400">
                    <span>{campaign.total_recipients} destinatários</span>
                    <span>•</span>
                    <span>{campaign.messages_sent} enviadas</span>
                    {campaign.messages_delivered > 0 && (
                      <>
                        <span>•</span>
                        <span>{campaign.messages_delivered} entregues</span>
                      </>
                    )}
                    {campaign.messages_failed > 0 && (
                      <>
                        <span>•</span>
                        <span className="text-red-500">{campaign.messages_failed} falhas</span>
                      </>
                    )}
                  </div>

                  {campaign.scheduled_at && campaign.status === 'scheduled' && (
                    <p className="text-sm text-blue-600 mt-1">
                      <ClockIcon className="w-4 h-4 inline mr-1" />
                      Agendada para {new Date(campaign.scheduled_at).toLocaleString('pt-BR')}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {/* Action Buttons based on status */}
                  {campaign.status === 'draft' && (
                    <Button
                      size="sm"
                      onClick={() => handleStartCampaign(campaign)}
                      disabled={actionLoading === campaign.id}
                    >
                      <PlayIcon className="w-4 h-4 mr-1" />
                      Iniciar
                    </Button>
                  )}

                  {campaign.status === 'scheduled' && (
                    <>
                      <Button
                        size="sm"
                        onClick={() => handleStartCampaign(campaign)}
                        disabled={actionLoading === campaign.id}
                      >
                        <PlayIcon className="w-4 h-4 mr-1" />
                        Iniciar Agora
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleCancelCampaign(campaign)}
                        disabled={actionLoading === campaign.id}
                      >
                        <StopIcon className="w-4 h-4" />
                      </Button>
                    </>
                  )}

                  {campaign.status === 'running' && (
                    <>
                      <Button
                        size="sm"
                        onClick={() => handleForceProcess(campaign)}
                        disabled={actionLoading === campaign.id}
                        title="Forçar processamento (útil se Celery não está rodando)"
                      >
                        <ArrowPathIcon className={`w-4 h-4 mr-1 ${actionLoading === campaign.id ? 'animate-spin' : ''}`} />
                        Processar
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handlePauseCampaign(campaign)}
                        disabled={actionLoading === campaign.id}
                      >
                        <PauseIcon className="w-4 h-4 mr-1" />
                        Pausar
                      </Button>
                    </>
                  )}

                  {campaign.status === 'paused' && (
                    <>
                      <Button
                        size="sm"
                        onClick={() => handleResumeCampaign(campaign)}
                        disabled={actionLoading === campaign.id}
                      >
                        <PlayIcon className="w-4 h-4 mr-1" />
                        Retomar
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleCancelCampaign(campaign)}
                        disabled={actionLoading === campaign.id}
                      >
                        <StopIcon className="w-4 h-4" />
                      </Button>
                    </>
                  )}

                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handleViewStats(campaign)}
                  >
                    <ChartBarIcon className="w-4 h-4" />
                  </Button>
                </div>
              </div>

              {/* Progress Bar for running campaigns */}
              {campaign.status === 'running' && campaign.total_recipients > 0 && (
                <div className="mt-4">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>Progresso</span>
                    <span>{Math.round((campaign.messages_sent / campaign.total_recipients) * 100)}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-green-500 h-2 rounded-full transition-all"
                      style={{ width: `${(campaign.messages_sent / campaign.total_recipients) * 100}%` }}
                    />
                  </div>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Stats Modal */}
      {selectedCampaign && stats && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-lg p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                Estatísticas da Campanha
              </h2>
              <button
                onClick={() => { setSelectedCampaign(null); setStats(null); }}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <h3 className="font-semibold text-gray-900 dark:text-white mb-1">{stats.name}</h3>
                {getStatusBadge(stats.status)}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="bg-gray-50 dark:bg-gray-700 p-3 rounded-lg">
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Total</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total_recipients}</p>
                </div>
                <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg">
                  <p className="text-sm text-blue-600">Enviadas</p>
                  <p className="text-2xl font-bold text-blue-700">{stats.messages_sent}</p>
                </div>
                <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-lg">
                  <p className="text-sm text-green-600">Entregues</p>
                  <p className="text-2xl font-bold text-green-700">{stats.messages_delivered}</p>
                </div>
                <div className="bg-purple-50 dark:bg-purple-900/20 p-3 rounded-lg">
                  <p className="text-sm text-purple-600">Lidas</p>
                  <p className="text-2xl font-bold text-purple-700">{stats.messages_read}</p>
                </div>
              </div>

              {stats.messages_failed > 0 && (
                <div className="bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
                  <p className="text-sm text-red-600">Falhas</p>
                  <p className="text-2xl font-bold text-red-700">{stats.messages_failed}</p>
                </div>
              )}

              <div className="pt-4 border-t space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-500">Taxa de Entrega</span>
                  <span className="font-medium">{stats.delivery_rate.toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Taxa de Leitura</span>
                  <span className="font-medium">{stats.read_rate.toFixed(1)}%</span>
                </div>
                {stats.pending > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Pendentes</span>
                    <span className="font-medium">{stats.pending}</span>
                  </div>
                )}
              </div>

              {stats.started_at && (
                <p className="text-xs text-gray-500">
                  Iniciada em {new Date(stats.started_at).toLocaleString('pt-BR')}
                </p>
              )}
              {stats.completed_at && (
                <p className="text-xs text-gray-500">
                  Concluída em {new Date(stats.completed_at).toLocaleString('pt-BR')}
                </p>
              )}
            </div>

            <div className="mt-6 flex justify-end">
              <Button variant="secondary" onClick={() => { setSelectedCampaign(null); setStats(null); }}>
                Fechar
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};

export default WhatsAppCampaignsPage;
