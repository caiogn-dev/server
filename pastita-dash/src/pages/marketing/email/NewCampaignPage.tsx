/**
 * New Email Campaign Page - Professional Revamp
 * 
 * Simplified flow:
 * 1. Choose template
 * 2. Customize content
 * 3. Select audience (All / Segment / Custom)
 * 4. Review & Send
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeftIcon,
  EnvelopeIcon,
  UserGroupIcon,
  PaperAirplaneIcon,
  EyeIcon,
  SparklesIcon,
  CheckCircleIcon,
  UsersIcon,
  TagIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Loading } from '../../../components/common';
import { useStore } from '../../../hooks';
import {
  marketingService,
  EmailTemplate,
  EMAIL_TEMPLATE_PRESETS,
} from '../../../services/marketingService';
import logger from '../../../services/logger';

// =============================================================================
// TYPES
// =============================================================================

type Step = 'template' | 'content' | 'audience' | 'review';
type AudienceType = 'all' | 'segment' | 'custom';

interface Subscriber {
  id: string;
  email: string;
  name: string;
  status: string;
  tags: string[];
  total_orders: number;
  total_spent: number;
}

interface SegmentFilters {
  tags: string[];
  minOrders: number | null;
  minSpent: number | null;
  hasOrdered: boolean | null;
}

interface CampaignData {
  name: string;
  subject: string;
  from_name: string;
  html_content: string;
  audienceType: AudienceType;
  segmentFilters: SegmentFilters;
  selectedSubscribers: string[];
  variables: Record<string, string>;
}

// =============================================================================
// CONSTANTS
// =============================================================================

const STEPS: { id: Step; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'template', label: 'Template', icon: SparklesIcon },
  { id: 'content', label: 'Conteúdo', icon: EnvelopeIcon },
  { id: 'audience', label: 'Audiência', icon: UserGroupIcon },
  { id: 'review', label: 'Enviar', icon: PaperAirplaneIcon },
];

const AUDIENCE_OPTIONS = [
  {
    type: 'all' as AudienceType,
    title: 'Todos os Contatos',
    description: 'Enviar para todos os subscribers ativos',
    icon: UsersIcon,
  },
  {
    type: 'segment' as AudienceType,
    title: 'Segmento',
    description: 'Filtrar por tags, compras, etc',
    icon: FunnelIcon,
  },
  {
    type: 'custom' as AudienceType,
    title: 'Lista Personalizada',
    description: 'Selecionar contatos específicos',
    icon: TagIcon,
  },
];

// =============================================================================
// COMPONENT
// =============================================================================

export const NewCampaignPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { storeId, storeName } = useStore();

  // State
  const [currentStep, setCurrentStep] = useState<Step>('template');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<EmailTemplate | null>(null);
  const [subscribers, setSubscribers] = useState<Subscriber[]>([]);
  const [subscriberSearch, setSubscriberSearch] = useState('');
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [showPreview, setShowPreview] = useState(false);

  const [campaignData, setCampaignData] = useState<CampaignData>({
    name: '',
    subject: '',
    from_name: storeName || 'Pastita',
    html_content: '',
    audienceType: 'all',
    segmentFilters: {
      tags: [],
      minOrders: null,
      minSpent: null,
      hasOrdered: null,
    },
    selectedSubscribers: [],
    variables: {},
  });

  // =============================================================================
  // DATA LOADING
  // =============================================================================

  useEffect(() => {
    const loadData = async () => {
      if (!storeId) return;
      setLoading(true);
      
      try {
        // Load templates and subscribers in parallel
        const [templatesData, subscribersData] = await Promise.all([
          marketingService.emailTemplates.list(storeId),
          marketingService.subscribers.list(storeId, { status: 'active' }),
        ]);

        setTemplates(templatesData);
        setSubscribers(subscribersData);

        // Extract unique tags
        const tags = new Set<string>();
        subscribersData.forEach(s => s.tags?.forEach(t => tags.add(t)));
        setAvailableTags(Array.from(tags));

        // Check for template in URL
        const templateSlug = searchParams.get('template');
        if (templateSlug) {
          const preset = templatesData.find(t => t.slug === templateSlug);
          if (preset) {
            handleSelectTemplate(preset);
          }
        }
      } catch (error) {
        logger.error('Failed to load data', error);
        toast.error('Erro ao carregar dados');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [storeId, searchParams]);

  // =============================================================================
  // COMPUTED VALUES
  // =============================================================================

  const filteredSubscribers = useMemo(() => {
    let result = subscribers;

    // Apply segment filters
    if (campaignData.audienceType === 'segment') {
      const { tags, minOrders, minSpent, hasOrdered } = campaignData.segmentFilters;
      
      if (tags.length > 0) {
        result = result.filter(s => tags.some(t => s.tags?.includes(t)));
      }
      if (minOrders !== null) {
        result = result.filter(s => s.total_orders >= minOrders);
      }
      if (minSpent !== null) {
        result = result.filter(s => s.total_spent >= minSpent);
      }
      if (hasOrdered === true) {
        result = result.filter(s => s.total_orders > 0);
      } else if (hasOrdered === false) {
        result = result.filter(s => s.total_orders === 0);
      }
    }

    // Apply search
    if (subscriberSearch) {
      const search = subscriberSearch.toLowerCase();
      result = result.filter(s => 
        s.email.toLowerCase().includes(search) ||
        s.name.toLowerCase().includes(search)
      );
    }

    return result;
  }, [subscribers, campaignData.audienceType, campaignData.segmentFilters, subscriberSearch]);

  const audienceCount = useMemo(() => {
    switch (campaignData.audienceType) {
      case 'all':
        return subscribers.length;
      case 'segment':
        return filteredSubscribers.length;
      case 'custom':
        return campaignData.selectedSubscribers.length;
      default:
        return 0;
    }
  }, [campaignData.audienceType, subscribers.length, filteredSubscribers.length, campaignData.selectedSubscribers.length]);

  // =============================================================================
  // HANDLERS
  // =============================================================================

  const handleSelectTemplate = (template: EmailTemplate) => {
    setSelectedTemplate(template);
    setCampaignData(prev => ({
      ...prev,
      name: `Campanha - ${template.name}`,
      subject: template.subject,
      html_content: template.html_content,
      variables: template.variables?.reduce((acc, v) => ({ ...acc, [v]: '' }), {}) || {},
    }));
    setCurrentStep('content');
  };

  const handleVariableChange = (key: string, value: string) => {
    setCampaignData(prev => ({
      ...prev,
      variables: { ...prev.variables, [key]: value },
    }));
  };

  const handleToggleSubscriber = (subscriberId: string) => {
    setCampaignData(prev => ({
      ...prev,
      selectedSubscribers: prev.selectedSubscribers.includes(subscriberId)
        ? prev.selectedSubscribers.filter(id => id !== subscriberId)
        : [...prev.selectedSubscribers, subscriberId],
    }));
  };

  const handleSelectAllFiltered = () => {
    setCampaignData(prev => ({
      ...prev,
      selectedSubscribers: filteredSubscribers.map(s => s.id),
    }));
  };

  const handleClearSelection = () => {
    setCampaignData(prev => ({
      ...prev,
      selectedSubscribers: [],
    }));
  };

  const getPreviewHtml = useCallback(() => {
    let html = campaignData.html_content;
    
    // Replace custom variables
    Object.entries(campaignData.variables).forEach(([key, value]) => {
      html = html.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), value || `{{${key}}}`);
    });
    
    // Replace system variables
    html = html.replace(/\{\{store_name\}\}/g, storeName || 'Loja');
    html = html.replace(/\{\{year\}\}/g, new Date().getFullYear().toString());
    
    return html;
  }, [campaignData.html_content, campaignData.variables, storeName]);

  const handleSendCampaign = async () => {
    if (!storeId) {
      toast.error('Selecione uma loja');
      return;
    }

    if (audienceCount === 0) {
      toast.error('Selecione pelo menos um destinatário');
      return;
    }

    setSending(true);
    try {
      const finalHtml = getPreviewHtml();
      
      // Build base payload
      const basePayload = {
        store: storeId,
        name: campaignData.name,
        subject: campaignData.subject,
        html_content: finalHtml,
        from_name: campaignData.from_name || storeName || 'Pastita',
        audience_type: campaignData.audienceType as 'all' | 'segment' | 'custom',
      };

      // Add audience-specific data
      let audienceData = {};
      if (campaignData.audienceType === 'segment') {
        audienceData = {
          audience_filters: {
            tags: campaignData.segmentFilters.tags,
            min_orders: campaignData.segmentFilters.minOrders,
            min_spent: campaignData.segmentFilters.minSpent,
          },
        };
      } else if (campaignData.audienceType === 'custom') {
        // Get selected subscriber details
        const selectedSubs = subscribers.filter(s => 
          campaignData.selectedSubscribers.includes(s.id)
        );
        audienceData = {
          recipient_list: selectedSubs.map(s => ({
            email: s.email,
            name: s.name,
          })),
        };
      }

      const payload = { ...basePayload, ...audienceData };
      logger.info('Creating campaign', { payload });

      // Create and send campaign
      const campaign = await marketingService.emailCampaigns.create(payload);
      const result = await marketingService.emailCampaigns.send(campaign.id);

      if (result.success) {
        toast.success(`🎉 Campanha enviada para ${audienceCount} contatos!`);
        navigate('/marketing');
      } else {
        toast.error(result.error || 'Erro ao enviar campanha');
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { error?: { message?: string } } } };
      logger.error('Failed to send campaign', error);
      toast.error(err.response?.data?.error?.message || 'Erro ao enviar campanha');
    } finally {
      setSending(false);
    }
  };

  // =============================================================================
  // NAVIGATION
  // =============================================================================

  const canProceed = () => {
    switch (currentStep) {
      case 'template':
        return !!selectedTemplate;
      case 'content':
        return !!campaignData.subject && !!campaignData.name;
      case 'audience':
        return audienceCount > 0;
      case 'review':
        return true;
      default:
        return false;
    }
  };

  const goToNextStep = () => {
    const currentIndex = STEPS.findIndex(s => s.id === currentStep);
    if (currentIndex < STEPS.length - 1) {
      setCurrentStep(STEPS[currentIndex + 1].id);
    }
  };

  const goToPrevStep = () => {
    const currentIndex = STEPS.findIndex(s => s.id === currentStep);
    if (currentIndex > 0) {
      setCurrentStep(STEPS[currentIndex - 1].id);
    }
  };

  // =============================================================================
  // RENDER
  // =============================================================================

  if (!storeId) {
    return (
      <div className="p-6 text-center">
        <EnvelopeIcon className="w-16 h-16 text-gray-300 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Nenhuma loja selecionada</h2>
        <p className="text-gray-500 dark:text-zinc-400 mb-4">Selecione uma loja para criar campanhas.</p>
        <Button onClick={() => navigate('/stores')}>Ver Lojas</Button>
      </div>
    );
  }

  if (loading) {
    return <Loading />;
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-black">
      {/* Header */}
      <div className="bg-white dark:bg-zinc-900 border-b sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/marketing')}
                className="p-2 hover:bg-gray-100 dark:hover:bg-zinc-700 dark:bg-gray-700 rounded-lg transition-colors"
              >
                <ArrowLeftIcon className="w-5 h-5" />
              </button>
              <div>
                <h1 className="text-xl font-bold text-gray-900 dark:text-white">Nova Campanha</h1>
                <p className="text-sm text-gray-500 dark:text-zinc-400">{storeName}</p>
              </div>
            </div>
            
            {/* Audience count badge */}
            {currentStep !== 'template' && (
              <div className="flex items-center gap-2 bg-primary-50 text-primary-700 px-3 py-1.5 rounded-full">
                <UsersIcon className="w-4 h-4" />
                <span className="font-medium">{audienceCount} destinatários</span>
              </div>
            )}
          </div>

          {/* Steps */}
          <div className="flex items-center gap-2 mt-4 overflow-x-auto pb-2">
            {STEPS.map((step, index) => {
              const Icon = step.icon;
              const isActive = step.id === currentStep;
              const isPast = STEPS.findIndex(s => s.id === currentStep) > index;

              return (
                <React.Fragment key={step.id}>
                  <button
                    onClick={() => isPast && setCurrentStep(step.id)}
                    disabled={!isPast && !isActive}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg whitespace-nowrap transition-colors ${
                      isActive
                        ? 'bg-primary-100 text-primary-700'
                        : isPast
                        ? 'bg-green-100 text-green-700 cursor-pointer hover:bg-green-200'
                        : 'bg-gray-100 text-gray-400'
                    }`}
                  >
                    {isPast ? (
                      <CheckCircleIcon className="w-5 h-5" />
                    ) : (
                      <Icon className="w-5 h-5" />
                    )}
                    <span className="font-medium">{step.label}</span>
                  </button>
                  {index < STEPS.length - 1 && (
                    <div className={`w-8 h-0.5 ${isPast ? 'bg-green-300' : 'bg-gray-200'}`} />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-5xl mx-auto px-4 py-6">
        {/* Step: Template */}
        {currentStep === 'template' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Escolha um Template</h2>
              <p className="text-gray-500 dark:text-zinc-400">Selecione um template para começar sua campanha.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {templates.map(template => (
                <button
                  key={template.id}
                  onClick={() => handleSelectTemplate(template)}
                  className={`bg-white rounded-xl border text-left cursor-pointer transition-all hover:shadow-lg ${
                    selectedTemplate?.id === template.id
                      ? 'ring-2 ring-primary-500 border-primary-500'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="h-32 bg-gradient-to-br from-primary-50 to-primary-100 relative overflow-hidden rounded-t-xl flex items-center justify-center">
                    <EnvelopeIcon className="w-12 h-12 text-primary-300" />
                  </div>
                  <div className="p-4">
                    <h3 className="font-semibold text-gray-900 dark:text-white">{template.name}</h3>
                    <p className="text-sm text-gray-500 dark:text-zinc-400 line-clamp-1">{template.subject}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step: Content */}
        {currentStep === 'content' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-6">
              <Card className="p-6">
                <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Informações da Campanha</h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                      Nome da Campanha
                    </label>
                    <input
                      type="text"
                      value={campaignData.name}
                      onChange={e => setCampaignData(prev => ({ ...prev, name: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                      placeholder="Ex: Promoção de Natal"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                      Assunto do Email
                    </label>
                    <input
                      type="text"
                      value={campaignData.subject}
                      onChange={e => setCampaignData(prev => ({ ...prev, subject: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                      placeholder="Ex: 🎁 Presente especial para você!"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                      Nome do Remetente
                    </label>
                    <input
                      type="text"
                      value={campaignData.from_name}
                      onChange={e => setCampaignData(prev => ({ ...prev, from_name: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                      placeholder="Ex: Pastita"
                    />
                  </div>
                </div>
              </Card>

              {/* Variables Info Card */}
              <Card className="p-6 bg-gradient-to-br from-blue-50 to-indigo-50 border-blue-200">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-blue-100 rounded-lg">
                    <SparklesIcon className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-blue-900 mb-2">Personalização Automática</h3>
                    <p className="text-sm text-blue-700 mb-3">
                      As variáveis do template serão preenchidas automaticamente com os dados de cada cliente:
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                        {'{{customer_name}}'} → Nome do cliente
                      </span>
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                        {'{{first_name}}'} → Primeiro nome
                      </span>
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                        {'{{email}}'} → Email
                      </span>
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                        {'{{store_name}}'} → Nome da loja
                      </span>
                    </div>
                  </div>
                </div>
              </Card>

              {/* Custom Variables (only for non-automatic variables like coupon_code) */}
              {selectedTemplate && selectedTemplate.variables && selectedTemplate.variables.filter(v => 
                !['customer_name', 'first_name', 'name', 'email', 'phone', 'store_name', 'store_url', 'year'].includes(v)
              ).length > 0 && (
                <Card className="p-6">
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Valores Personalizados</h3>
                  <p className="text-sm text-gray-500 dark:text-zinc-400 mb-4">
                    Preencha os valores específicos desta campanha:
                  </p>
                  <div className="space-y-4">
                    {selectedTemplate.variables
                      .filter(v => !['customer_name', 'first_name', 'name', 'email', 'phone', 'store_name', 'store_url', 'year'].includes(v))
                      .map(variable => (
                        <div key={variable}>
                          <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                            {variable.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </label>
                          <input
                            type="text"
                            value={campaignData.variables[variable] || ''}
                            onChange={e => handleVariableChange(variable, e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                            placeholder={`Ex: ${variable === 'coupon_code' ? 'DESCONTO10' : variable === 'discount_value' ? '10%' : variable === 'expiry_date' ? '31/12/2026' : ''}`}
                          />
                        </div>
                      ))}
                  </div>
                </Card>
              )}
            </div>

            <div>
              <Card className="p-4 sticky top-32">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-gray-900 dark:text-white">Preview</h3>
                  <Button variant="secondary" size="sm" onClick={() => setShowPreview(true)}>
                    <EyeIcon className="w-4 h-4 mr-1" />
                    Expandir
                  </Button>
                </div>
                <div className="border rounded-lg overflow-hidden bg-gray-100 dark:bg-gray-700" style={{ height: '400px' }}>
                  <iframe srcDoc={getPreviewHtml()} className="w-full h-full" title="Preview" />
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* Step: Audience */}
        {currentStep === 'audience' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Selecione a Audiência</h2>
              <p className="text-gray-500 dark:text-zinc-400">
                Você tem <strong>{subscribers.length}</strong> contatos ativos.
              </p>
            </div>

            {/* Audience Type Selection */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {AUDIENCE_OPTIONS.map(option => {
                const Icon = option.icon;
                const isSelected = campaignData.audienceType === option.type;
                
                return (
                  <button
                    key={option.type}
                    onClick={() => setCampaignData(prev => ({ 
                      ...prev, 
                      audienceType: option.type,
                      selectedSubscribers: option.type === 'all' ? [] : prev.selectedSubscribers,
                    }))}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${
                      isSelected
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-gray-200 hover:border-gray-300 bg-white'
                    }`}
                  >
                    <Icon className={`w-8 h-8 mb-2 ${isSelected ? 'text-primary-600' : 'text-gray-400'}`} />
                    <h3 className={`font-semibold ${isSelected ? 'text-primary-900' : 'text-gray-900'}`}>
                      {option.title}
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-zinc-400">{option.description}</p>
                  </button>
                );
              })}
            </div>

            {/* Segment Filters */}
            {campaignData.audienceType === 'segment' && (
              <Card className="p-6">
                <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Filtros do Segmento</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Tags */}
                  {availableTags.length > 0 && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">Tags</label>
                      <div className="flex flex-wrap gap-2">
                        {availableTags.map(tag => (
                          <button
                            key={tag}
                            onClick={() => {
                              setCampaignData(prev => ({
                                ...prev,
                                segmentFilters: {
                                  ...prev.segmentFilters,
                                  tags: prev.segmentFilters.tags.includes(tag)
                                    ? prev.segmentFilters.tags.filter(t => t !== tag)
                                    : [...prev.segmentFilters.tags, tag],
                                },
                              }));
                            }}
                            className={`px-3 py-1 rounded-full text-sm transition-colors ${
                              campaignData.segmentFilters.tags.includes(tag)
                                ? 'bg-primary-100 text-primary-700'
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                            }`}
                          >
                            {tag}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Min Orders */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">
                      Mínimo de Pedidos
                    </label>
                    <input
                      type="number"
                      min="0"
                      value={campaignData.segmentFilters.minOrders ?? ''}
                      onChange={e => setCampaignData(prev => ({
                        ...prev,
                        segmentFilters: {
                          ...prev.segmentFilters,
                          minOrders: e.target.value ? parseInt(e.target.value) : null,
                        },
                      }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                      placeholder="Ex: 1"
                    />
                  </div>

                  {/* Has Ordered */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">
                      Histórico de Compras
                    </label>
                    <select
                      value={campaignData.segmentFilters.hasOrdered === null ? '' : String(campaignData.segmentFilters.hasOrdered)}
                      onChange={e => setCampaignData(prev => ({
                        ...prev,
                        segmentFilters: {
                          ...prev.segmentFilters,
                          hasOrdered: e.target.value === '' ? null : e.target.value === 'true',
                        },
                      }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                    >
                      <option value="">Todos</option>
                      <option value="true">Já compraram</option>
                      <option value="false">Nunca compraram</option>
                    </select>
                  </div>
                </div>

                <div className="mt-4 p-3 bg-gray-50 dark:bg-black rounded-lg">
                  <p className="text-sm text-gray-600 dark:text-zinc-400">
                    <strong>{filteredSubscribers.length}</strong> contatos correspondem aos filtros
                  </p>
                </div>
              </Card>
            )}

            {/* Custom Selection */}
            {campaignData.audienceType === 'custom' && (
              <Card className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-semibold text-gray-900 dark:text-white">Selecionar Contatos</h3>
                  <div className="flex gap-2">
                    <Button variant="secondary" size="sm" onClick={handleSelectAllFiltered}>
                      Selecionar Todos
                    </Button>
                    <Button variant="secondary" size="sm" onClick={handleClearSelection}>
                      Limpar
                    </Button>
                  </div>
                </div>

                {/* Search */}
                <div className="relative mb-4">
                  <MagnifyingGlassIcon className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    value={subscriberSearch}
                    onChange={e => setSubscriberSearch(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                    placeholder="Buscar por email ou nome..."
                  />
                </div>

                {/* Subscriber List */}
                <div className="border rounded-lg divide-y max-h-80 overflow-y-auto">
                  {filteredSubscribers.length === 0 ? (
                    <div className="p-8 text-center text-gray-500 dark:text-zinc-400">
                      Nenhum contato encontrado
                    </div>
                  ) : (
                    filteredSubscribers.map(subscriber => (
                      <label
                        key={subscriber.id}
                        className="flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={campaignData.selectedSubscribers.includes(subscriber.id)}
                          onChange={() => handleToggleSubscriber(subscriber.id)}
                          className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-gray-900 dark:text-white truncate">{subscriber.email}</p>
                          {subscriber.name && (
                            <p className="text-sm text-gray-500 dark:text-zinc-400 truncate">{subscriber.name}</p>
                          )}
                        </div>
                        {subscriber.total_orders > 0 && (
                          <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                            {subscriber.total_orders} pedidos
                          </span>
                        )}
                      </label>
                    ))
                  )}
                </div>

                <p className="text-sm text-gray-500 dark:text-zinc-400 mt-4">
                  {campaignData.selectedSubscribers.length} de {filteredSubscribers.length} selecionados
                </p>
              </Card>
            )}

            {/* Summary */}
            <Card className="p-4 bg-primary-50 border-primary-200">
              <div className="flex items-center gap-3">
                <UsersIcon className="w-8 h-8 text-primary-600" />
                <div>
                  <p className="font-semibold text-primary-900">
                    {audienceCount} {audienceCount === 1 ? 'destinatário' : 'destinatários'}
                  </p>
                  <p className="text-sm text-primary-700">
                    {campaignData.audienceType === 'all' && 'Todos os contatos ativos'}
                    {campaignData.audienceType === 'segment' && 'Contatos que correspondem aos filtros'}
                    {campaignData.audienceType === 'custom' && 'Contatos selecionados manualmente'}
                  </p>
                </div>
              </div>
            </Card>
          </div>
        )}

        {/* Step: Review */}
        {currentStep === 'review' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-6">
              <Card className="p-6">
                <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Resumo da Campanha</h3>
                <dl className="space-y-3">
                  <div className="flex justify-between py-2 border-b">
                    <dt className="text-gray-500 dark:text-zinc-400">Nome</dt>
                    <dd className="font-medium text-gray-900 dark:text-white">{campaignData.name}</dd>
                  </div>
                  <div className="flex justify-between py-2 border-b">
                    <dt className="text-gray-500 dark:text-zinc-400">Assunto</dt>
                    <dd className="font-medium text-gray-900 dark:text-white">{campaignData.subject}</dd>
                  </div>
                  <div className="flex justify-between py-2 border-b">
                    <dt className="text-gray-500 dark:text-zinc-400">Remetente</dt>
                    <dd className="font-medium text-gray-900 dark:text-white">{campaignData.from_name}</dd>
                  </div>
                  <div className="flex justify-between py-2 border-b">
                    <dt className="text-gray-500 dark:text-zinc-400">Template</dt>
                    <dd className="font-medium text-gray-900 dark:text-white">{selectedTemplate?.name}</dd>
                  </div>
                  <div className="flex justify-between py-2">
                    <dt className="text-gray-500 dark:text-zinc-400">Destinatários</dt>
                    <dd className="font-medium text-primary-600">{audienceCount} contatos</dd>
                  </div>
                </dl>
              </Card>

              <Card className="p-6 bg-amber-50 border-amber-200">
                <h3 className="font-semibold text-amber-800 mb-2 flex items-center gap-2">
                  <PaperAirplaneIcon className="w-5 h-5" />
                  Pronto para enviar?
                </h3>
                <p className="text-amber-700 text-sm">
                  Ao clicar em "Enviar Campanha", os emails serão disparados imediatamente 
                  para {audienceCount} {audienceCount === 1 ? 'contato' : 'contatos'}.
                </p>
              </Card>
            </div>

            <div>
              <Card className="p-4 sticky top-32">
                <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Preview Final</h3>
                <div className="border rounded-lg overflow-hidden bg-gray-100 dark:bg-gray-700" style={{ height: '400px' }}>
                  <iframe srcDoc={getPreviewHtml()} className="w-full h-full" title="Preview" />
                </div>
              </Card>
            </div>
          </div>
        )}

        {/* Navigation */}
        <div className="flex items-center justify-between mt-8 pt-6 border-t">
          <Button
            variant="secondary"
            onClick={goToPrevStep}
            disabled={currentStep === 'template'}
          >
            <ArrowLeftIcon className="w-5 h-5 mr-2" />
            Voltar
          </Button>

          {currentStep === 'review' ? (
            <Button
              onClick={handleSendCampaign}
              disabled={sending || audienceCount === 0}
              className="bg-green-600 hover:bg-green-700 text-white"
            >
              {sending ? (
                <>
                  <div className="w-5 h-5 mr-2 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Enviando...
                </>
              ) : (
                <>
                  <PaperAirplaneIcon className="w-5 h-5 mr-2" />
                  Enviar para {audienceCount} contatos
                </>
              )}
            </Button>
          ) : (
            <Button onClick={goToNextStep} disabled={!canProceed()}>
              Próximo
            </Button>
          )}
        </div>
      </div>

      {/* Full Preview Modal */}
      {showPreview && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-zinc-900 rounded-xl w-full max-w-4xl max-h-[90vh] overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="font-semibold">Preview do Email</h3>
              <button
                onClick={() => setShowPreview(false)}
                className="p-2 hover:bg-gray-100 dark:hover:bg-zinc-700 dark:bg-gray-700 rounded-lg"
              >
                ✕
              </button>
            </div>
            <div className="p-4" style={{ height: 'calc(90vh - 80px)' }}>
              <iframe srcDoc={getPreviewHtml()} className="w-full h-full border rounded-lg" title="Preview" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default NewCampaignPage;
