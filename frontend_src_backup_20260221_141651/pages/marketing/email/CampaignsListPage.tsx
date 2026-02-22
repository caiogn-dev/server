/**
 * Email Campaigns List Page
 * 
 * Lists all email campaigns with status, stats, and actions.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PlusIcon,
  PaperAirplaneIcon,
  PauseIcon,
  PlayIcon,
  TrashIcon,
  EyeIcon,
  ChartBarIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  EnvelopeIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import toast from 'react-hot-toast';
import { Card, Button, Modal, Loading } from '../../../components/common';
import { useStore } from '../../../hooks';
import api from '@/services/api';

interface EmailCampaign {
  id: string;
  name: string;
  subject: string;
  status: 'draft' | 'scheduled' | 'sending' | 'sent' | 'paused' | 'cancelled';
  audience_type: string;
  total_recipients: number;
  emails_sent: number;
  emails_delivered: number;
  emails_opened: number;
  emails_clicked: number;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

interface CampaignRecipient {
  id: string;
  email: string;
  name: string;
  status: 'pending' | 'sent' | 'delivered' | 'opened' | 'clicked' | 'bounced' | 'failed';
  sent_at: string | null;
  opened_at: string | null;
  clicked_at: string | null;
  error_message: string | null;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ComponentType<{ className?: string }> }> = {
  draft: { label: 'Rascunho', color: 'bg-gray-100 text-gray-700', icon: ClockIcon },
  scheduled: { label: 'Agendada', color: 'bg-blue-100 text-blue-700', icon: ClockIcon },
  sending: { label: 'Enviando', color: 'bg-yellow-100 text-yellow-700', icon: ArrowPathIcon },
  sent: { label: 'Enviada', color: 'bg-green-100 text-green-700', icon: CheckCircleIcon },
  paused: { label: 'Pausada', color: 'bg-orange-100 text-orange-700', icon: PauseIcon },
  cancelled: { label: 'Cancelada', color: 'bg-red-100 text-red-700', icon: XCircleIcon },
};

const AUDIENCE_LABELS: Record<string, string> = {
  all: 'Todos',
  customers: 'Clientes',
  subscribers: 'Inscritos',
  segment: 'Segmento',
  custom: 'Personalizado',
};

export const CampaignsListPage: React.FC = () => {
  const navigate = useNavigate();
  const { storeId } = useStore();
  
  const [loading, setLoading] = useState(true);
  const [campaigns, setCampaigns] = useState<EmailCampaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<EmailCampaign | null>(null);
  const [recipients, setRecipients] = useState<CampaignRecipient[]>([]);
  const [loadingRecipients, setLoadingRecipients] = useState(false);
  const [showRecipientsModal, setShowRecipientsModal] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadCampaigns = useCallback(async () => {
    try {
      setLoading(true);
      console.log('Loading campaigns, storeId:', storeId);
      
      const params: Record<string, string> = {};
      if (storeId) {
        params.store = storeId;
      }
      
      const response = await api.get(`/marketing/campaigns/`, { params });
      console.log('Campaigns response:', response.data);
      
      const data = response.data.results || response.data || [];
      setCampaigns(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Error loading campaigns:', error);
      toast.error('Erro ao carregar campanhas');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    loadCampaigns();
  }, [loadCampaigns]);

  const loadRecipients = async (campaignId: string) => {
    try {
      setLoadingRecipients(true);
      const response = await api.get(`/marketing/campaigns/${campaignId}/recipients/`);
      setRecipients(response.data.results || response.data || []);
    } catch (error) {
      console.error('Error loading recipients:', error);
      toast.error('Erro ao carregar destinatários');
    } finally {
      setLoadingRecipients(false);
    }
  };

  const handleViewRecipients = async (campaign: EmailCampaign) => {
    setSelectedCampaign(campaign);
    setShowRecipientsModal(true);
    await loadRecipients(campaign.id);
  };

  const handleSendCampaign = async (campaign: EmailCampaign) => {
    if (!confirm(`Enviar campanha "${campaign.name}" agora?`)) return;
    
    try {
      setActionLoading(campaign.id);
      const response = await api.post(`/marketing/campaigns/${campaign.id}/send/`);
      toast.success(`Campanha enviada! ${response.data.sent} emails enviados.`);
      loadCampaigns();
    } catch (error: any) {
      toast.error(error.response?.data?.error || 'Erro ao enviar campanha');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteCampaign = async (campaign: EmailCampaign) => {
    if (!confirm(`Excluir campanha "${campaign.name}"?`)) return;
    
    try {
      setActionLoading(campaign.id);
      await api.delete(`/marketing/campaigns/${campaign.id}/`);
      toast.success('Campanha excluída');
      loadCampaigns();
    } catch (error) {
      toast.error('Erro ao excluir campanha');
    } finally {
      setActionLoading(null);
    }
  };

  const getOpenRate = (campaign: EmailCampaign) => {
    if (!campaign.emails_delivered || campaign.emails_delivered === 0) return 0;
    return ((campaign.emails_opened / campaign.emails_delivered) * 100).toFixed(1);
  };

  const getClickRate = (campaign: EmailCampaign) => {
    if (!campaign.emails_opened || campaign.emails_opened === 0) return 0;
    return ((campaign.emails_clicked / campaign.emails_opened) * 100).toFixed(1);
  };

  if (loading) {
    return <Loading />;
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Campanhas de Email</h1>
          <p className="text-gray-500 dark:text-zinc-400">{campaigns.length} campanha(s)</p>
        </div>
        <Button onClick={() => navigate('/marketing/email/new')}>
          <PlusIcon className="w-5 h-5 mr-2" />
          Nova Campanha
        </Button>
      </div>

      {campaigns.length === 0 ? (
        <Card className="p-12 text-center">
          <EnvelopeIcon className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Nenhuma campanha criada</h3>
          <p className="text-gray-500 dark:text-zinc-400 mb-6">Crie sua primeira campanha de email marketing</p>
          <Button onClick={() => navigate('/marketing/email/new')}>
            <PlusIcon className="w-5 h-5 mr-2" />
            Criar Campanha
          </Button>
        </Card>
      ) : (
        <div className="space-y-4">
          {campaigns.map((campaign) => {
            const statusConfig = STATUS_CONFIG[campaign.status] || STATUS_CONFIG.draft;
            const StatusIcon = statusConfig.icon;
            
            return (
              <Card key={campaign.id} className="p-4 hover:shadow-md transition-shadow">
                <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                  {/* Campaign Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="font-semibold text-gray-900 dark:text-white truncate">{campaign.name}</h3>
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${statusConfig.color}`}>
                        <StatusIcon className="w-3 h-3" />
                        {statusConfig.label}
                      </span>
                    </div>
                    <p className="text-sm text-gray-500 dark:text-zinc-400 truncate mb-2">{campaign.subject}</p>
                    <div className="flex flex-wrap items-center gap-4 text-xs text-gray-400">
                      <span>Audiência: {AUDIENCE_LABELS[campaign.audience_type] || campaign.audience_type}</span>
                      <span>Criada: {format(new Date(campaign.created_at), "dd/MM/yyyy 'às' HH:mm", { locale: ptBR })}</span>
                      {campaign.completed_at && (
                        <span>Enviada: {format(new Date(campaign.completed_at), "dd/MM/yyyy 'às' HH:mm", { locale: ptBR })}</span>
                      )}
                    </div>
                  </div>

                  {/* Stats */}
                  {campaign.status === 'sent' && (
                    <div className="flex items-center gap-6 px-4 py-2 bg-gray-50 dark:bg-black rounded-lg">
                      <div className="text-center">
                        <p className="text-lg font-bold text-gray-900 dark:text-white">{campaign.emails_sent}</p>
                        <p className="text-xs text-gray-500 dark:text-zinc-400">Enviados</p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-bold text-blue-600">{getOpenRate(campaign)}%</p>
                        <p className="text-xs text-gray-500 dark:text-zinc-400">Abertura</p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-bold text-green-600">{getClickRate(campaign)}%</p>
                        <p className="text-xs text-gray-500 dark:text-zinc-400">Cliques</p>
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {campaign.status === 'draft' && (
                      <Button
                        size="sm"
                        onClick={() => handleSendCampaign(campaign)}
                        disabled={actionLoading === campaign.id}
                      >
                        {actionLoading === campaign.id ? (
                          <ArrowPathIcon className="w-4 h-4 animate-spin" />
                        ) : (
                          <>
                            <PaperAirplaneIcon className="w-4 h-4 mr-1" />
                            Enviar
                          </>
                        )}
                      </Button>
                    )}
                    
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleViewRecipients(campaign)}
                    >
                      <EyeIcon className="w-4 h-4 mr-1" />
                      Detalhes
                    </Button>

                    {campaign.status === 'draft' && (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => handleDeleteCampaign(campaign)}
                        disabled={actionLoading === campaign.id}
                      >
                        <TrashIcon className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Recipients Modal */}
      <Modal
        isOpen={showRecipientsModal}
        onClose={() => {
          setShowRecipientsModal(false);
          setSelectedCampaign(null);
          setRecipients([]);
        }}
        title={`Destinatários - ${selectedCampaign?.name || ''}`}
        size="xl"
      >
        {loadingRecipients ? (
          <div className="py-12 text-center">
            <ArrowPathIcon className="w-8 h-8 text-gray-400 animate-spin mx-auto mb-2" />
            <p className="text-gray-500 dark:text-zinc-400">Carregando destinatários...</p>
          </div>
        ) : recipients.length === 0 ? (
          <div className="py-12 text-center">
            <EnvelopeIcon className="w-12 h-12 text-gray-300 mx-auto mb-2" />
            <p className="text-gray-500 dark:text-zinc-400">Nenhum destinatário encontrado</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Summary */}
            <div className="grid grid-cols-4 gap-4 p-4 bg-gray-50 dark:bg-black rounded-lg">
              <div className="text-center">
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{recipients.length}</p>
                <p className="text-xs text-gray-500 dark:text-zinc-400">Total</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-green-600">
                  {recipients.filter(r => r.status === 'sent' || r.status === 'delivered' || r.status === 'opened' || r.status === 'clicked').length}
                </p>
                <p className="text-xs text-gray-500 dark:text-zinc-400">Enviados</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-600">
                  {recipients.filter(r => r.status === 'opened' || r.status === 'clicked').length}
                </p>
                <p className="text-xs text-gray-500 dark:text-zinc-400">Abertos</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-red-600">
                  {recipients.filter(r => r.status === 'failed' || r.status === 'bounced').length}
                </p>
                <p className="text-xs text-gray-500 dark:text-zinc-400">Falhas</p>
              </div>
            </div>

            {/* Recipients List */}
            <div className="max-h-96 overflow-y-auto">
              <table className="w-full">
                <thead className="bg-gray-50 dark:bg-black sticky top-0">
                  <tr>
                    <th className="text-left text-xs font-medium text-gray-500 dark:text-zinc-400 px-4 py-2">Email</th>
                    <th className="text-left text-xs font-medium text-gray-500 dark:text-zinc-400 px-4 py-2">Nome</th>
                    <th className="text-left text-xs font-medium text-gray-500 dark:text-zinc-400 px-4 py-2">Status</th>
                    <th className="text-left text-xs font-medium text-gray-500 dark:text-zinc-400 px-4 py-2">Enviado em</th>
                    <th className="text-left text-xs font-medium text-gray-500 dark:text-zinc-400 px-4 py-2">Erro</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {recipients.map((recipient) => (
                    <tr key={recipient.id} className="hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black">
                      <td className="px-4 py-2 text-sm text-gray-900 dark:text-white">{recipient.email}</td>
                      <td className="px-4 py-2 text-sm text-gray-500 dark:text-zinc-400">{recipient.name || '-'}</td>
                      <td className="px-4 py-2">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          recipient.status === 'sent' || recipient.status === 'delivered' ? 'bg-green-100 text-green-700' :
                          recipient.status === 'opened' || recipient.status === 'clicked' ? 'bg-blue-100 text-blue-700' :
                          recipient.status === 'failed' || recipient.status === 'bounced' ? 'bg-red-100 text-red-700' :
                          'bg-gray-100 text-gray-700'
                        }`}>
                          {recipient.status}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-sm text-gray-500 dark:text-zinc-400">
                        {recipient.sent_at ? format(new Date(recipient.sent_at), "dd/MM HH:mm") : '-'}
                      </td>
                      <td className="px-4 py-2 text-sm text-red-500 max-w-xs truncate" title={recipient.error_message || ''}>
                        {recipient.error_message || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default CampaignsListPage;
