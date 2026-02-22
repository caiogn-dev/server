import React, { useEffect, useState, useCallback } from 'react';
import { PaperAirplaneIcon, TableCellsIcon, ChatBubbleLeftRightIcon, MagnifyingGlassIcon, ArrowPathIcon, FunnelIcon } from '@heroicons/react/24/outline';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import toast from 'react-hot-toast';
import { Card, Button, Input, Textarea, Select, Modal, PageLoading, StatusBadge, Table, PageTitle } from '../../components/common';
import { ChatWindow } from '../../components/chat';
import { whatsappService, getErrorMessage } from '../../services';
import { useAccountStore } from '../../stores/accountStore';
import { Conversation, Message } from '../../types';

type ViewMode = 'chat' | 'table';
type MessageFilter = 'all' | 'inbound' | 'outbound';

export const MessagesPage: React.FC = () => {
  const { accounts, selectedAccount, setSelectedAccount } = useAccountStore();
  const [viewMode, setViewMode] = useState<ViewMode>('chat');
  const [sendModal, setSendModal] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [messageForm, setMessageForm] = useState({
    account_id: '',
    to: '',
    text: '',
    type: 'text',
  });
  
  // Table view states
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filter, setFilter] = useState<MessageFilter>('all');
  const [dateRange, setDateRange] = useState<{ start: string; end: string }>({ start: '', end: '' });

  const loadMessages = useCallback(async () => {
    if (!selectedAccount) return;
    setIsLoadingMessages(true);
    try {
      const params: Record<string, string> = {};
      if (searchQuery) {
        params.search = searchQuery;
      }
      if (filter !== 'all') {
        params.direction = filter;
      }
      if (dateRange.start) {
        params.created_after = dateRange.start;
      }
      if (dateRange.end) {
        params.created_before = dateRange.end;
      }
      const response = await whatsappService.getMessages(selectedAccount.id, params);
      setMessages(response.results || []);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsLoadingMessages(false);
    }
  }, [selectedAccount, searchQuery, filter, dateRange]);

  useEffect(() => {
    if (viewMode === 'table') {
      loadMessages();
    }
  }, [viewMode, loadMessages]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSending(true);
    try {
      await whatsappService.sendTextMessage({
        account_id: messageForm.account_id,
        to: messageForm.to,
        text: messageForm.text,
      });
      toast.success('Mensagem enviada com sucesso!');
      setSendModal(false);
      setMessageForm({ account_id: '', to: '', text: '', type: 'text' });
      if (viewMode === 'table') {
        loadMessages();
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsSending(false);
    }
  };

  const handleConversationSelect = (conversation: Conversation | null) => {
    setSelectedConversation(conversation);
  };

  useEffect(() => {
    if (!selectedAccount && accounts.length > 0) {
      setSelectedAccount(accounts[0]);
    }
  }, [accounts, selectedAccount, setSelectedAccount]);

  // Table columns configuration
  const messageColumns = [
    {
      key: 'direction',
      header: 'Direção',
      render: (msg: Message) => (
        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
          msg.direction === 'inbound' 
            ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300' 
            : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
        }`}>
          {msg.direction === 'inbound' ? '← Recebida' : '→ Enviada'}
        </span>
      ),
    },
    {
      key: 'contact',
      header: 'Contato',
      render: (msg: Message) => (
        <div>
          <p className="font-medium text-gray-900 dark:text-white">
            {msg.direction === 'inbound' ? msg.from_number : msg.to_number}
          </p>
          <p className="text-sm text-gray-500 dark:text-zinc-400">{msg.account_name}</p>
        </div>
      ),
    },
    {
      key: 'content',
      header: 'Conteúdo',
      render: (msg: Message) => (
        <div className="max-w-md">
          <p className="text-sm text-gray-900 dark:text-white truncate">
            {msg.text_body || `[${msg.message_type}]`}
          </p>
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Tipo',
      render: (msg: Message) => (
        <span className="text-sm text-gray-600 dark:text-zinc-400 capitalize">{msg.message_type}</span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (msg: Message) => <StatusBadge status={msg.status} />,
    },
    {
      key: 'created_at',
      header: 'Data',
      render: (msg: Message) => (
        <span className="text-sm text-gray-600 dark:text-zinc-400">
          {format(new Date(msg.created_at), "dd/MM/yyyy HH:mm", { locale: ptBR })}
        </span>
      ),
    },
  ];

  // Show loading if no account selected
  if (!selectedAccount) {
    return (
      <div className="p-6">
        <PageTitle
          title="Mensagens"
          subtitle="Selecione uma conta WhatsApp"
        />
        <Card className="flex flex-col items-center justify-center py-12">
            <ChatBubbleLeftRightIcon className="w-16 h-16 text-gray-300 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Nenhuma conta selecionada
            </h3>
            <p className="text-gray-500 dark:text-zinc-400 text-center max-w-md">
              Selecione uma conta WhatsApp no menu superior para visualizar e gerenciar suas conversas.
            </p>
          </Card>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col p-6">
      <PageTitle
        title="Mensagens"
        subtitle={selectedConversation 
          ? `Conversa com ${selectedConversation.contact_name || selectedConversation.phone_number}`
          : `${selectedAccount.name}`
        }
        actions={
          <div className="flex items-center gap-2">
            {/* View mode toggle */}
            <div className="flex items-center bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
              <button
                onClick={() => setViewMode('chat')}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  viewMode === 'chat'
                    ? 'bg-white dark:bg-gray-600 text-primary-600 dark:text-primary-400 shadow-sm'
                    : 'text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                <ChatBubbleLeftRightIcon className="w-4 h-4" />
                Chat
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  viewMode === 'table'
                    ? 'bg-white dark:bg-gray-600 text-primary-600 dark:text-primary-400 shadow-sm'
                    : 'text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                <TableCellsIcon className="w-4 h-4" />
                Tabela
              </button>
            </div>

            <Button
              leftIcon={<PaperAirplaneIcon className="w-5 h-5" />}
              onClick={() => {
                setMessageForm({ ...messageForm, account_id: selectedAccount.id });
                setSendModal(true);
              }}
            >
              Nova Mensagem
            </Button>
          </div>
        }
      />

      <div className="flex-1 overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <label className="text-sm font-medium text-gray-600 dark:text-zinc-300">
            Conta WhatsApp:
          </label>
          <select
            value={selectedAccount?.id || ''}
            onChange={(e) => {
              const account = accounts.find((a) => a.id === e.target.value);
              setSelectedAccount(account || null);
            }}
            className="px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg text-sm bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-[#722F37] focus:border-[#722F37]"
          >
            <option value="">Todas as contas</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </div>
        {viewMode === 'chat' ? (
          <div className="h-full" style={{ minHeight: 'calc(100vh - 200px)' }}>
            <ChatWindow
              accountId={selectedAccount.id}
              accountName={selectedAccount.name}
              onConversationSelect={handleConversationSelect}
            />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Filters Bar */}
            <Card className="p-4">
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex-1 min-w-[200px]">
                  <div className="relative">
                    <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                    <input
                      type="text"
                      placeholder="Buscar mensagens..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && loadMessages()}
                      className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg text-sm bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  <FunnelIcon className="w-5 h-5 text-gray-400" />
                  <select
                    value={filter}
                    onChange={(e) => setFilter(e.target.value as MessageFilter)}
                    className="px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg text-sm bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="all">Todas</option>
                    <option value="inbound">Recebidas</option>
                    <option value="outbound">Enviadas</option>
                  </select>
                </div>
                
                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    value={dateRange.start}
                    onChange={(e) => setDateRange(prev => ({ ...prev, start: e.target.value }))}
                    className="px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg text-sm bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                  <span className="text-gray-500">até</span>
                  <input
                    type="date"
                    value={dateRange.end}
                    onChange={(e) => setDateRange(prev => ({ ...prev, end: e.target.value }))}
                    className="px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg text-sm bg-white dark:bg-zinc-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
                
                <Button
                  variant="secondary"
                  leftIcon={<ArrowPathIcon className={`w-4 h-4 ${isLoadingMessages ? 'animate-spin' : ''}`} />}
                  onClick={loadMessages}
                  isLoading={isLoadingMessages}
                >
                  Atualizar
                </Button>
              </div>
            </Card>
            
            {/* Messages Table */}
            <Card noPadding>
              {isLoadingMessages ? (
                <PageLoading />
              ) : (
                <Table
                  columns={messageColumns}
                  data={messages}
                  keyExtractor={(msg) => msg.id}
                  emptyMessage="Nenhuma mensagem encontrada"
                />
              )}
            </Card>
            
            
            <div className="text-sm text-gray-500 dark:text-zinc-400 text-center">
              {messages.length} mensagem(ns) encontrada(s)
            </div>
          </div>
        )}
      </div>

      {/* Send Message Modal */}
      <Modal
        isOpen={sendModal}
        onClose={() => setSendModal(false)}
        title="Enviar Nova Mensagem"
        size="md"
      >
        <form onSubmit={handleSendMessage} className="space-y-4">
          <Select
            label="Conta WhatsApp"
            required
            value={messageForm.account_id}
            onChange={(e) => setMessageForm({ ...messageForm, account_id: e.target.value })}
            options={[
              { value: '', label: 'Selecione uma conta' },
              ...accounts.map((acc) => ({ value: acc.id, label: acc.name })),
            ]}
          />
          <Input
            label="Número de Destino"
            required
            value={messageForm.to}
            onChange={(e) => setMessageForm({ ...messageForm, to: e.target.value })}
            placeholder="5511999999999"
            helperText="Digite o número com código do país (ex: 5511999999999)"
          />
          <Textarea
            label="Mensagem"
            required
            rows={4}
            value={messageForm.text}
            onChange={(e) => setMessageForm({ ...messageForm, text: e.target.value })}
            placeholder="Digite sua mensagem..."
          />
          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setSendModal(false)}>
              Cancelar
            </Button>
            <Button type="submit" isLoading={isSending}>
              Enviar
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
