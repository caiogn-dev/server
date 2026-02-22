/**
 * New WhatsApp Campaign Page
 * 
 * Flow:
 * 1. Select WhatsApp account
 * 2. Choose message type (template or text)
 * 3. Configure message content
 * 4. Add recipients (manual, CSV, or contact list)
 * 5. Review & Send/Schedule
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeftIcon,
  DevicePhoneMobileIcon,
  UserGroupIcon,
  PaperAirplaneIcon,
  CheckCircleIcon,
  UsersIcon,
  DocumentTextIcon,
  ClockIcon,
  PlusIcon,
  TrashIcon,
  ArrowUpTrayIcon,
  ChatBubbleLeftRightIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Loading, Modal, Input } from '../../../components/common';
import { whatsappService } from '../../../services/whatsapp';
import { campaignsService, Campaign, ContactList } from '../../../services/campaigns';
import { WhatsAppAccount, MessageTemplate, PaginatedResponse } from '../../../types';

// Local type definitions for campaign page
type ContactInput = { phone: string; name?: string };
type SystemContact = { 
  phone: string; 
  name: string; 
  last_message_at?: string;
  source?: 'conversation' | 'order' | 'subscriber' | 'session';
};
import logger from '../../../services/logger';

// =============================================================================
// TYPES
// =============================================================================

type Step = 'account' | 'message' | 'recipients' | 'review';
type MessageType = 'template' | 'text';

interface CampaignFormData {
  name: string;
  description: string;
  accountId: string;
  messageType: MessageType;
  templateId: string;
  templateName: string;
  templateLanguage: string;
  textContent: string;
  contacts: Array<{ phone: string; name?: string }>;
  scheduledAt: string;
  messagesPerMinute: number;
}

// =============================================================================
// CONSTANTS
// =============================================================================

const STEPS: { id: Step; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'account', label: 'Conta', icon: DevicePhoneMobileIcon },
  { id: 'message', label: 'Mensagem', icon: ChatBubbleLeftRightIcon },
  { id: 'recipients', label: 'Destinatários', icon: UserGroupIcon },
  { id: 'review', label: 'Enviar', icon: PaperAirplaneIcon },
];

// =============================================================================
// COMPONENT
// =============================================================================

export const NewWhatsAppCampaignPage: React.FC = () => {
  const navigate = useNavigate();

  // State
  const [currentStep, setCurrentStep] = useState<Step>('account');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [accounts, setAccounts] = useState<WhatsAppAccount[]>([]);
  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [contactLists, setContactLists] = useState<Array<{ id: string; name: string; contact_count: number; contacts: ContactInput[] }>>([]);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showSystemContactsModal, setShowSystemContactsModal] = useState(false);
  const [csvContent, setCsvContent] = useState('');
  const [newContact, setNewContact] = useState({ phone: '', name: '' });
  const [systemContacts, setSystemContacts] = useState<SystemContact[]>([]);
  const [loadingSystemContacts, setLoadingSystemContacts] = useState(false);
  const [selectedSystemContacts, setSelectedSystemContacts] = useState<Set<string>>(new Set());

  const [formData, setFormData] = useState<CampaignFormData>({
    name: '',
    description: '',
    accountId: '',
    messageType: 'template',
    templateId: '',
    templateName: '',
    templateLanguage: 'pt_BR',
    textContent: '',
    contacts: [],
    scheduledAt: '',
    messagesPerMinute: 60,
  });

  // =============================================================================
  // DATA LOADING
  // =============================================================================

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        // Load accounts (required)
        const accountsRes = await whatsappService.getAccounts();
        const accountsList = accountsRes.results || [];
        setAccounts(accountsList);

        // Auto-select first account if only one
        if (accountsList.length === 1) {
          setFormData(prev => ({ ...prev, accountId: accountsList[0].id }));
        }

        // Try to load contact lists (optional)
        try {
          const contactListsRes = await campaignsService.getContactLists();
          setContactLists(contactListsRes.results || []);
        } catch {
          setContactLists([]);
        }
      } catch (error) {
        logger.error('Failed to load accounts', error);
        setAccounts([]);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  // Load templates when account is selected
  useEffect(() => {
    const loadTemplates = async () => {
      if (!formData.accountId) return;

      try {
        const templatesRes = await whatsappService.getTemplates(formData.accountId);
        const templatesList = templatesRes.results || [];
        setTemplates(templatesList.filter(t => t.status === 'approved'));
      } catch (error) {
        logger.error('Failed to load templates', error);
        setTemplates([]);
      }
    };

    loadTemplates();
  }, [formData.accountId]);

  // =============================================================================
  // COMPUTED VALUES
  // =============================================================================

  const selectedAccount = useMemo(() => 
    accounts.find(a => a.id === formData.accountId),
    [accounts, formData.accountId]
  );

  const selectedTemplate = useMemo(() =>
    templates.find(t => t.id === formData.templateId),
    [templates, formData.templateId]
  );

  const recipientCount = formData.contacts.length;

  // =============================================================================
  // HANDLERS
  // =============================================================================

  const handleAccountSelect = (accountId: string) => {
    setFormData(prev => ({
      ...prev,
      accountId,
      templateId: '',
      templateName: '',
    }));
    setCurrentStep('message');
  };

  const handleTemplateSelect = (template: MessageTemplate) => {
    setFormData(prev => ({
      ...prev,
      templateId: template.id,
      templateName: template.name,
      templateLanguage: template.language,
      name: prev.name || `Campanha - ${template.name}`,
    }));
  };

  const handleLoadSystemContacts = async () => {
    setLoadingSystemContacts(true);
    setShowSystemContactsModal(true);
    try {
      // Load conversations as system contacts
      const { conversationsService } = await import('../../../services/conversations');
      const params: Record<string, string> = { limit: '500' };
      if (formData.accountId) params.account = formData.accountId;
      const response = await conversationsService.getConversations(params);
      const contacts: SystemContact[] = response.results.map(conv => ({
        phone: conv.phone_number,
        name: conv.contact_name || conv.phone_number,
        last_message_at: conv.last_message_at || undefined,
        source: 'conversation',
      }));
      setSystemContacts(contacts);
      setSelectedSystemContacts(new Set());
    } catch (error) {
      logger.error('Failed to load system contacts', error);
      toast.error('Erro ao carregar contatos');
      setSystemContacts([]);
    } finally {
      setLoadingSystemContacts(false);
    }
  };

  const handleToggleSystemContact = (phone: string) => {
    setSelectedSystemContacts(prev => {
      const newSet = new Set(prev);
      if (newSet.has(phone)) {
        newSet.delete(phone);
      } else {
        newSet.add(phone);
      }
      return newSet;
    });
  };

  const handleSelectAllSystemContacts = () => {
    if (selectedSystemContacts.size === systemContacts.length) {
      setSelectedSystemContacts(new Set());
    } else {
      setSelectedSystemContacts(new Set(systemContacts.map(c => c.phone)));
    }
  };

  const handleAddSystemContacts = () => {
    const existingPhones = new Set(formData.contacts.map(c => c.phone));
    const newContacts: ContactInput[] = [];

    systemContacts.forEach(contact => {
      if (selectedSystemContacts.has(contact.phone) && !existingPhones.has(contact.phone)) {
        newContacts.push({ phone: contact.phone, name: contact.name });
      }
    });

    if (newContacts.length === 0) {
      toast.error('Nenhum contato novo selecionado');
      return;
    }

    setFormData(prev => ({
      ...prev,
      contacts: [...prev.contacts, ...newContacts],
    }));

    toast.success(`${newContacts.length} contatos adicionados`);
    setShowSystemContactsModal(false);
    setSelectedSystemContacts(new Set());
  };

  const handleAddContact = () => {
    if (!newContact.phone) {
      toast.error('Informe o número de telefone');
      return;
    }

    // Clean phone number
    const cleanPhone = newContact.phone.replace(/\D/g, '');
    
    // Check for duplicates
    if (formData.contacts.some(c => c.phone.replace(/\D/g, '') === cleanPhone)) {
      toast.error('Este número já foi adicionado');
      return;
    }

    setFormData(prev => ({
      ...prev,
      contacts: [...prev.contacts, { phone: cleanPhone, name: newContact.name }],
    }));
    setNewContact({ phone: '', name: '' });
  };

  const handleRemoveContact = (index: number) => {
    setFormData(prev => ({
      ...prev,
      contacts: prev.contacts.filter((_, i) => i !== index),
    }));
  };

  const handleImportCSV = () => {
    if (!csvContent.trim()) {
      toast.error('Cole o conteúdo do CSV');
      return;
    }

    try {
      const lines = csvContent.trim().split('\n');
      const newContacts: ContactInput[] = [];

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        // Skip header if present
        if (i === 0 && (line.toLowerCase().includes('phone') || line.toLowerCase().includes('telefone'))) {
          continue;
        }

        const parts = line.split(/[,;\t]/);
        const phone = parts[0]?.replace(/\D/g, '');
        const name = parts[1]?.trim() || '';

        if (phone && phone.length >= 10) {
          newContacts.push({ phone, name });
        }
      }

      if (newContacts.length === 0) {
        toast.error('Nenhum contato válido encontrado');
        return;
      }

      // Merge with existing, avoiding duplicates
      const existingPhones = new Set(formData.contacts.map(c => c.phone));
      const uniqueNew = newContacts.filter(c => !existingPhones.has(c.phone));

      setFormData(prev => ({
        ...prev,
        contacts: [...prev.contacts, ...uniqueNew],
      }));

      toast.success(`${uniqueNew.length} contatos importados`);
      setShowImportModal(false);
      setCsvContent('');
    } catch (error) {
      logger.error('CSV import error', error);
      toast.error('Erro ao processar CSV');
    }
  };

  const handleLoadContactList = async (listId: string) => {
    try {
      const list = await campaignsService.getContactList(listId);
      
      // Merge contacts
      const existingPhones = new Set(formData.contacts.map(c => c.phone));
      const uniqueNew = list.contacts.filter((c: { phone: string }) => !existingPhones.has(c.phone));

      setFormData(prev => ({
        ...prev,
        contacts: [...prev.contacts, ...uniqueNew],
      }));

      toast.success(`${uniqueNew.length} contatos adicionados da lista "${list.name}"`);
    } catch (error) {
      logger.error('Failed to load contact list', error);
      toast.error('Erro ao carregar lista de contatos');
    }
  };

  const handleSendCampaign = async (schedule: boolean = false) => {
    if (!formData.accountId) {
      toast.error('Selecione uma conta WhatsApp');
      return;
    }

    if (formData.messageType === 'template' && !formData.templateId) {
      toast.error('Selecione um template');
      return;
    }

    if (formData.messageType === 'text' && !formData.textContent.trim()) {
      toast.error('Digite o conteúdo da mensagem');
      return;
    }

    if (formData.contacts.length === 0) {
      toast.error('Adicione pelo menos um destinatário');
      return;
    }

    if (schedule && !formData.scheduledAt) {
      toast.error('Selecione a data/hora do agendamento');
      return;
    }

    setSending(true);
    try {
      // Build campaign payload
      const payload = {
        account_id: formData.accountId,
        name: formData.name || `Campanha WhatsApp - ${new Date().toLocaleDateString('pt-BR')}`,
        description: formData.description,
        campaign_type: 'broadcast' as const,
        template_id: formData.messageType === 'template' ? formData.templateId : undefined,
        message_content: formData.messageType === 'text' 
          ? { text: formData.textContent }
          : { template_name: formData.templateName, language: formData.templateLanguage },
        contact_list: formData.contacts,
        scheduled_at: schedule ? formData.scheduledAt : undefined,
        messages_per_minute: formData.messagesPerMinute,
      };

      logger.info('Creating WhatsApp campaign', { payload });

      // Create campaign
      const campaign = await campaignsService.createCampaign(payload);

      if (schedule) {
        // Schedule the campaign
        await campaignsService.scheduleCampaign(campaign.id, formData.scheduledAt);
        toast.success(`🎉 Campanha agendada para ${new Date(formData.scheduledAt).toLocaleString('pt-BR')}`);
      } else {
        // Start immediately
        await campaignsService.startCampaign(campaign.id);
        toast.success(`🎉 Campanha iniciada! Enviando para ${recipientCount} contatos...`);
      }

      navigate('/marketing/whatsapp');
    } catch (error: unknown) {
      const err = error as { response?: { data?: { error?: string } } };
      logger.error('Failed to create campaign', error);
      toast.error(err.response?.data?.error || 'Erro ao criar campanha');
    } finally {
      setSending(false);
      setShowScheduleModal(false);
    }
  };

  // =============================================================================
  // NAVIGATION
  // =============================================================================

  const canProceed = () => {
    switch (currentStep) {
      case 'account':
        return !!formData.accountId;
      case 'message':
        return formData.messageType === 'template' 
          ? !!formData.templateId 
          : !!formData.textContent.trim();
      case 'recipients':
        return formData.contacts.length > 0;
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

  if (loading) {
    return <Loading />;
  }

  if (accounts.length === 0) {
    return (
      <div className="p-6 text-center">
        <DevicePhoneMobileIcon className="w-16 h-16 text-gray-300 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Nenhuma conta WhatsApp</h2>
        <p className="text-gray-500 dark:text-zinc-400 mb-4">Configure uma conta WhatsApp para criar campanhas.</p>
        <Button onClick={() => navigate('/accounts/new')}>Adicionar Conta</Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-black">
      {/* Header */}
      <div className="bg-white dark:bg-zinc-900 border-b sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/marketing/whatsapp')}
                className="p-2 hover:bg-gray-100 dark:hover:bg-zinc-700 rounded-lg transition-colors"
              >
                <ArrowLeftIcon className="w-5 h-5" />
              </button>
              <div>
                <h1 className="text-xl font-bold text-gray-900 dark:text-white">Nova Campanha WhatsApp</h1>
                {selectedAccount && (
                  <p className="text-sm text-gray-500 dark:text-zinc-400">
                    {selectedAccount.name} • {selectedAccount.display_phone_number || selectedAccount.phone_number}
                  </p>
                )}
              </div>
            </div>
            
            {/* Recipient count badge */}
            {currentStep !== 'account' && recipientCount > 0 && (
              <div className="flex items-center gap-2 bg-green-50 text-green-700 px-3 py-1.5 rounded-full">
                <UsersIcon className="w-4 h-4" />
                <span className="font-medium">{recipientCount} destinatários</span>
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
                        ? 'bg-green-100 text-green-700'
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
        {/* Step: Account Selection */}
        {currentStep === 'account' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Selecione a Conta WhatsApp
              </h2>
              <p className="text-gray-500 dark:text-zinc-400">
                Escolha a conta que será usada para enviar as mensagens
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {accounts.map((account) => (
                <button
                  key={account.id}
                  onClick={() => handleAccountSelect(account.id)}
                  className={`p-4 rounded-xl border-2 text-left transition-all ${
                    formData.accountId === account.id
                      ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                      : 'border-gray-200 dark:border-zinc-800 hover:border-green-300'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${
                      account.status === 'active' ? 'bg-green-100' : 'bg-gray-100'
                    }`}>
                      <DevicePhoneMobileIcon className={`w-6 h-6 ${
                        account.status === 'active' ? 'text-green-600' : 'text-gray-400'
                      }`} />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900 dark:text-white">{account.name}</h3>
                      <p className="text-sm text-gray-500 dark:text-zinc-400">
                        {account.display_phone_number || account.phone_number}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      account.status === 'active' 
                        ? 'bg-green-100 text-green-700' 
                        : 'bg-gray-100 text-gray-600'
                    }`}>
                      {account.status === 'active' ? 'Ativa' : account.status}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step: Message Configuration */}
        {currentStep === 'message' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Configure a Mensagem
              </h2>
              <p className="text-gray-500 dark:text-zinc-400">
                Escolha o tipo de mensagem e configure o conteúdo
              </p>
            </div>

            {/* Campaign Name */}
            <Card className="p-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">
                Nome da Campanha
              </label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                placeholder="Ex: Promoção de Janeiro"
              />
            </Card>

            {/* Message Type Selection */}
            <div className="grid grid-cols-2 gap-4">
              <button
                onClick={() => setFormData(prev => ({ ...prev, messageType: 'template' }))}
                className={`p-4 rounded-xl border-2 text-left transition-all ${
                  formData.messageType === 'template'
                    ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                    : 'border-gray-200 dark:border-zinc-800 hover:border-green-300'
                }`}
              >
                <DocumentTextIcon className="w-8 h-8 text-green-600 mb-2" />
                <h3 className="font-semibold text-gray-900 dark:text-white">Template</h3>
                <p className="text-sm text-gray-500 dark:text-zinc-400">
                  Use um template aprovado pelo WhatsApp
                </p>
              </button>

              <button
                onClick={() => setFormData(prev => ({ ...prev, messageType: 'text' }))}
                className={`p-4 rounded-xl border-2 text-left transition-all ${
                  formData.messageType === 'text'
                    ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                    : 'border-gray-200 dark:border-zinc-800 hover:border-green-300'
                }`}
              >
                <ChatBubbleLeftRightIcon className="w-8 h-8 text-blue-600 mb-2" />
                <h3 className="font-semibold text-gray-900 dark:text-white">Texto Livre</h3>
                <p className="text-sm text-gray-500 dark:text-zinc-400">
                  Envie uma mensagem de texto personalizada
                </p>
              </button>
            </div>

            {/* Template Selection */}
            {formData.messageType === 'template' && (
              <Card className="p-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">
                  Selecione o Template
                </label>
                {templates.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <DocumentTextIcon className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                    <p>Nenhum template aprovado encontrado</p>
                    <Button 
                      variant="secondary" 
                      size="sm" 
                      className="mt-2"
                      onClick={() => whatsappService.syncTemplates(formData.accountId).then(() => {
                        toast.success('Templates sincronizados');
                        // Reload templates
                        whatsappService.getTemplates(formData.accountId)
                          .then(res => setTemplates(res.results.filter(t => t.status === 'approved')));
                      })}
                    >
                      Sincronizar Templates
                    </Button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {templates.map((template) => (
                      <button
                        key={template.id}
                        onClick={() => handleTemplateSelect(template)}
                        className={`p-3 rounded-lg border text-left transition-all ${
                          formData.templateId === template.id
                            ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                            : 'border-gray-200 dark:border-zinc-800 hover:border-green-300'
                        }`}
                      >
                        <h4 className="font-medium text-gray-900 dark:text-white">{template.name}</h4>
                        <p className="text-xs text-gray-500 mt-1">
                          {template.category} • {template.language}
                        </p>
                      </button>
                    ))}
                  </div>
                )}
              </Card>
            )}

            {/* Text Content */}
            {formData.messageType === 'text' && (
              <Card className="p-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">
                  Mensagem
                </label>
                <textarea
                  value={formData.textContent}
                  onChange={(e) => setFormData(prev => ({ ...prev, textContent: e.target.value }))}
                  placeholder="Digite sua mensagem aqui..."
                  rows={6}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
                />
                <p className="text-xs text-gray-500 mt-2">
                  Use {"{{nome}}"} para personalizar com o nome do contato
                </p>
              </Card>
            )}
          </div>
        )}

        {/* Step: Recipients */}
        {currentStep === 'recipients' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Adicione os Destinatários
              </h2>
              <p className="text-gray-500 dark:text-zinc-400">
                Adicione os contatos que receberão a mensagem
              </p>
            </div>

            {/* Add Contact Form */}
            <Card className="p-4">
              <h3 className="font-medium text-gray-900 dark:text-white mb-3">Adicionar Contato</h3>
              <div className="flex gap-3">
                <Input
                  value={newContact.phone}
                  onChange={(e) => setNewContact(prev => ({ ...prev, phone: e.target.value }))}
                  placeholder="Telefone (ex: 5511999999999)"
                  className="flex-1"
                />
                <Input
                  value={newContact.name}
                  onChange={(e) => setNewContact(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="Nome (opcional)"
                  className="flex-1"
                />
                <Button onClick={handleAddContact}>
                  <PlusIcon className="w-5 h-5" />
                </Button>
              </div>
            </Card>

            {/* Import Options */}
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" onClick={handleLoadSystemContacts}>
                <UserGroupIcon className="w-5 h-5 mr-2" />
                Carregar do Sistema
              </Button>
              
              <Button variant="secondary" onClick={() => setShowImportModal(true)}>
                <ArrowUpTrayIcon className="w-5 h-5 mr-2" />
                Importar CSV
              </Button>
              
              {contactLists.length > 0 && (
                <select
                  onChange={(e) => e.target.value && handleLoadContactList(e.target.value)}
                  className="px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  defaultValue=""
                >
                  <option value="">Carregar lista salva...</option>
                  {contactLists.map((list) => (
                    <option key={list.id} value={list.id}>
                      {list.name} ({list.contact_count} contatos)
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Contact List */}
            <Card className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-medium text-gray-900 dark:text-white">
                  Contatos ({formData.contacts.length})
                </h3>
                {formData.contacts.length > 0 && (
                  <Button 
                    variant="secondary" 
                    size="sm"
                    onClick={() => setFormData(prev => ({ ...prev, contacts: [] }))}
                  >
                    Limpar Todos
                  </Button>
                )}
              </div>

              {formData.contacts.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <UserGroupIcon className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                  <p>Nenhum contato adicionado</p>
                </div>
              ) : (
                <div className="max-h-64 overflow-y-auto space-y-2">
                  {formData.contacts.map((contact, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700 rounded-lg"
                    >
                      <div>
                        <span className="font-medium text-gray-900 dark:text-white">
                          {contact.phone}
                        </span>
                        {contact.name && (
                          <span className="text-gray-500 dark:text-zinc-400 ml-2">
                            ({contact.name})
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => handleRemoveContact(index)}
                        className="p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                      >
                        <TrashIcon className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}

        {/* Step: Review */}
        {currentStep === 'review' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Revise e Envie
              </h2>
              <p className="text-gray-500 dark:text-zinc-400">
                Confira os detalhes da campanha antes de enviar
              </p>
            </div>

            {/* Summary */}
            <Card className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Campanha</p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {formData.name || 'Sem nome'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Conta</p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {selectedAccount?.name}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Tipo de Mensagem</p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {formData.messageType === 'template' ? 'Template' : 'Texto Livre'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-zinc-400">Destinatários</p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {recipientCount} contatos
                  </p>
                </div>
              </div>

              {formData.messageType === 'template' && selectedTemplate && (
                <div className="pt-4 border-t">
                  <p className="text-sm text-gray-500 dark:text-zinc-400 mb-1">Template</p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {selectedTemplate.name}
                  </p>
                </div>
              )}

              {formData.messageType === 'text' && (
                <div className="pt-4 border-t">
                  <p className="text-sm text-gray-500 dark:text-zinc-400 mb-1">Mensagem</p>
                  <p className="text-gray-900 dark:text-white whitespace-pre-wrap bg-gray-50 dark:bg-gray-700 p-3 rounded-lg">
                    {formData.textContent}
                  </p>
                </div>
              )}

              {/* Rate Limiting */}
              <div className="pt-4 border-t">
                <label className="block text-sm text-gray-500 dark:text-zinc-400 mb-2">
                  Velocidade de Envio
                </label>
                <select
                  value={formData.messagesPerMinute}
                  onChange={(e) => setFormData(prev => ({ ...prev, messagesPerMinute: Number(e.target.value) }))}
                  className="px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  <option value={30}>30 mensagens/minuto (Conservador)</option>
                  <option value={60}>60 mensagens/minuto (Recomendado)</option>
                  <option value={120}>120 mensagens/minuto (Rápido)</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  Tempo estimado: ~{Math.ceil(recipientCount / formData.messagesPerMinute)} minutos
                </p>
              </div>
            </Card>

            {/* Warning */}
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
              <p className="text-sm text-yellow-800 dark:text-yellow-200">
                ⚠️ <strong>Atenção:</strong> Certifique-se de que todos os contatos consentiram em receber mensagens. 
                O envio de spam pode resultar em bloqueio da sua conta WhatsApp Business.
              </p>
            </div>
          </div>
        )}

        {/* Navigation Buttons */}
        <div className="flex items-center justify-between mt-8 pt-6 border-t">
          <Button
            variant="secondary"
            onClick={goToPrevStep}
            disabled={currentStep === 'account'}
          >
            <ArrowLeftIcon className="w-5 h-5 mr-2" />
            Voltar
          </Button>

          <div className="flex gap-3">
            {currentStep === 'review' ? (
              <>
                <Button
                  variant="secondary"
                  onClick={() => setShowScheduleModal(true)}
                  disabled={sending}
                >
                  <ClockIcon className="w-5 h-5 mr-2" />
                  Agendar
                </Button>
                <Button
                  onClick={() => handleSendCampaign(false)}
                  disabled={sending || !canProceed()}
                >
                  {sending ? (
                    <>
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                      Enviando...
                    </>
                  ) : (
                    <>
                      <PaperAirplaneIcon className="w-5 h-5 mr-2" />
                      Enviar Agora
                    </>
                  )}
                </Button>
              </>
            ) : (
              <Button onClick={goToNextStep} disabled={!canProceed()}>
                Continuar
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Schedule Modal */}
      <Modal
        isOpen={showScheduleModal}
        onClose={() => setShowScheduleModal(false)}
        title="Agendar Campanha"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">
              Data e Hora
            </label>
            <input
              type="datetime-local"
              value={formData.scheduledAt}
              onChange={(e) => setFormData(prev => ({ ...prev, scheduledAt: e.target.value }))}
              min={new Date().toISOString().slice(0, 16)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
            />
          </div>
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setShowScheduleModal(false)}>
              Cancelar
            </Button>
            <Button onClick={() => handleSendCampaign(true)} disabled={sending || !formData.scheduledAt}>
              {sending ? 'Agendando...' : 'Confirmar Agendamento'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Import CSV Modal */}
      <Modal
        isOpen={showImportModal}
        onClose={() => setShowImportModal(false)}
        title="Importar Contatos do CSV"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-zinc-400">
            Cole o conteúdo do CSV abaixo. Formato esperado: telefone,nome (uma linha por contato)
          </p>
          <textarea
            value={csvContent}
            onChange={(e) => setCsvContent(e.target.value)}
            placeholder="5511999999999,João Silva&#10;5511888888888,Maria Santos"
            rows={8}
            className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent dark:bg-gray-700 dark:text-white font-mono text-sm"
          />
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setShowImportModal(false)}>
              Cancelar
            </Button>
            <Button onClick={handleImportCSV}>
              Importar
            </Button>
          </div>
        </div>
      </Modal>

      {/* System Contacts Modal */}
      <Modal
        isOpen={showSystemContactsModal}
        onClose={() => setShowSystemContactsModal(false)}
        title="Contatos do Sistema"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-zinc-400">
            Selecione os contatos que deseja adicionar à campanha
          </p>
          
          {loadingSystemContacts ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-8 h-8 border-4 border-green-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : systemContacts.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <UserGroupIcon className="w-12 h-12 mx-auto mb-2 text-gray-300" />
              <p>Nenhum contato encontrado no sistema</p>
            </div>
          ) : (
            <>
              {/* Select All */}
              <div className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700 rounded-lg">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedSystemContacts.size === systemContacts.length}
                    onChange={handleSelectAllSystemContacts}
                    className="w-4 h-4 text-green-600 rounded focus:ring-green-500"
                  />
                  <span className="font-medium text-gray-900 dark:text-white">
                    Selecionar todos ({systemContacts.length})
                  </span>
                </label>
                <span className="text-sm text-gray-500">
                  {selectedSystemContacts.size} selecionados
                </span>
              </div>

              {/* Contact List */}
              <div className="max-h-64 overflow-y-auto space-y-1 border rounded-lg p-2">
                {systemContacts.map((contact) => (
                  <label
                    key={contact.phone}
                    className="flex items-center gap-3 p-2 hover:bg-gray-50 dark:hover:bg-zinc-700 rounded cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedSystemContacts.has(contact.phone)}
                      onChange={() => handleToggleSystemContact(contact.phone)}
                      className="w-4 h-4 text-green-600 rounded focus:ring-green-500"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-gray-900 dark:text-white truncate">
                        {contact.phone}
                      </p>
                      {contact.name && (
                        <p className="text-sm text-gray-500 dark:text-zinc-400 truncate">
                          {contact.name}
                        </p>
                      )}
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      contact.source === 'conversation' ? 'bg-blue-100 text-blue-700' :
                      contact.source === 'order' ? 'bg-green-100 text-green-700' :
                      contact.source === 'subscriber' ? 'bg-purple-100 text-purple-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {contact.source === 'conversation' ? 'Conversa' :
                       contact.source === 'order' ? 'Pedido' :
                       contact.source === 'subscriber' ? 'Inscrito' :
                       contact.source === 'session' ? 'Sessão' : contact.source}
                    </span>
                  </label>
                ))}
              </div>
            </>
          )}

          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setShowSystemContactsModal(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleAddSystemContacts}
              disabled={selectedSystemContacts.size === 0}
            >
              Adicionar {selectedSystemContacts.size > 0 ? `(${selectedSystemContacts.size})` : ''}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default NewWhatsAppCampaignPage;
