import React, { useEffect, useState, useMemo } from 'react';
import { format, formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import toast from 'react-hot-toast';
import { 
  MagnifyingGlassIcon, 
  ChatBubbleLeftRightIcon, 
  UserIcon, 
  CpuChipIcon,
  TagIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import { 
  Card, 
  Button, 
  Table, 
  ConversationStatusBadge,
  ConversationModeBadge,
  Modal, 
  Textarea, 
  Input,
  PageLoading,
  StatusTabs,
  PageTitle,
  CONVERSATION_STATUS_CONFIG,
  CONVERSATION_MODE_CONFIG,
} from '../../components/common';
import { conversationsService, ordersService, exportService, getErrorMessage } from '../../services';
import { useAccountStore } from '../../stores/accountStore';
import { useStore } from '../../hooks';
import { Conversation, ConversationNote, Order } from '../../types';

export const ConversationsPage: React.FC = () => {
  const { selectedAccount } = useAccountStore();
  const { storeSlug, storeId: contextStoreId } = useStore();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationOrders, setConversationOrders] = useState<Record<string, Order[]>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [detailConversation, setDetailConversation] = useState<Conversation | null>(null);
  const [notes, setNotes] = useState<ConversationNote[]>([]);
  const [newNote, setNewNote] = useState('');
  const [newTag, setNewTag] = useState('');
  const [isAddingNote, setIsAddingNote] = useState(false);
  const [isAddingTag, setIsAddingTag] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [modeFilter, setModeFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadConversations();
  }, [selectedAccount, storeSlug, contextStoreId]);

  const loadConversations = async () => {
    setIsLoading(true);
    try {
      const params: Record<string, string> = {};
      if (selectedAccount) {
        params.account = selectedAccount.id;
      }
      const response = await conversationsService.getConversations(params);
      setConversations(response.results);
      
      // Load orders for each conversation to show order status indicators
      const ordersMap: Record<string, Order[]> = {};
      for (const conv of response.results) {
        try {
          const orders = await ordersService.getByCustomer(
            conv.phone_number,
            storeSlug || contextStoreId || undefined
          );
          if (orders.length > 0) {
            ordersMap[conv.id] = orders;
          }
        } catch {
          // Ignore errors for individual order lookups
        }
      }
      setConversationOrders(ordersMap);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

  // Calculate status counts
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    conversations.forEach((conv) => {
      counts[conv.status] = (counts[conv.status] || 0) + 1;
    });
    return counts;
  }, [conversations]);

  // Calculate mode counts
  const modeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    conversations.forEach((conv) => {
      counts[conv.mode] = (counts[conv.mode] || 0) + 1;
    });
    return counts;
  }, [conversations]);

  // Filter conversations
  const filteredConversations = useMemo(() => {
    let result = conversations;
    
    if (statusFilter) {
      result = result.filter((conv) => conv.status === statusFilter);
    }
    
    if (modeFilter) {
      result = result.filter((conv) => conv.mode === modeFilter);
    }
    
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter((conv) =>
        conv.contact_name?.toLowerCase().includes(query) ||
        conv.phone_number.includes(query) ||
        conv.tags.some(tag => tag.toLowerCase().includes(query))
      );
    }
    
    return result;
  }, [conversations, statusFilter, modeFilter, searchQuery]);

  // Get order status summary for a conversation
  const getOrderSummary = (convId: string) => {
    const orders = conversationOrders[convId] || [];
    if (orders.length === 0) return null;
    
    const pending = orders.filter(o => ['pending', 'processing'].includes(o.status)).length;
    const paid = orders.filter(o => o.payment_status === 'paid' || ['paid', 'confirmed'].includes(o.status)).length;
    const shipped = orders.filter(o => ['shipped', 'out_for_delivery'].includes(o.status)).length;
    const delivered = orders.filter(o => ['delivered', 'completed'].includes(o.status)).length;
    
    return { total: orders.length, pending, paid, shipped, delivered };
  };

  const handleSwitchMode = async (conversation: Conversation, mode: 'human' | 'auto') => {
    try {
      const updated = mode === 'human'
        ? await conversationsService.switchToHuman(conversation.id)
        : await conversationsService.switchToAuto(conversation.id);
      setConversations(conversations.map((c) => (c.id === updated.id ? updated : c)));
      toast.success(`Modo alterado para ${mode === 'human' ? 'humano' : 'automático'}`);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const handleCloseConversation = async (conversation: Conversation) => {
    try {
      const updated = await conversationsService.closeConversation(conversation.id);
      setConversations(conversations.map((c) => (c.id === updated.id ? updated : c)));
      toast.success('Conversa fechada');
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const handleResolveConversation = async (conversation: Conversation) => {
    try {
      const updated = await conversationsService.resolveConversation(conversation.id);
      setConversations(conversations.map((c) => (c.id === updated.id ? updated : c)));
      toast.success('Conversa resolvida');
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const handleReopenConversation = async (conversation: Conversation) => {
    try {
      const updated = await conversationsService.reopenConversation(conversation.id);
      setConversations(conversations.map((c) => (c.id === updated.id ? updated : c)));
      toast.success('Conversa reaberta');
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const loadNotes = async (conversation: Conversation) => {
    try {
      const notesData = await conversationsService.getNotes(conversation.id);
      setNotes(notesData);
      setSelectedConversation(conversation);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const handleAddNote = async () => {
    if (!selectedConversation || !newNote.trim()) return;
    setIsAddingNote(true);
    try {
      const note = await conversationsService.addNote(selectedConversation.id, newNote);
      setNotes([note, ...notes]);
      setNewNote('');
      toast.success('Nota adicionada');
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsAddingNote(false);
    }
  };

  const handleAddTag = async () => {
    if (!detailConversation || !newTag.trim()) return;
    setIsAddingTag(true);
    try {
      const updated = await conversationsService.addTag(detailConversation.id, newTag.trim());
      setConversations(conversations.map((c) => (c.id === updated.id ? updated : c)));
      setDetailConversation(updated);
      setNewTag('');
      toast.success('Tag adicionada');
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsAddingTag(false);
    }
  };

  const handleRemoveTag = async (tag: string) => {
    if (!detailConversation) return;
    try {
      const updated = await conversationsService.removeTag(detailConversation.id, tag);
      setConversations(conversations.map((c) => (c.id === updated.id ? updated : c)));
      setDetailConversation(updated);
      toast.success('Tag removida');
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const handleExport = async (format: 'csv' | 'xlsx') => {
    setIsExporting(true);
    try {
      const blob = await exportService.exportConversations({
        format,
        status: statusFilter || undefined,
        mode: modeFilter || undefined,
        account_id: selectedAccount?.id,
      });
      const dateStamp = new Date().toISOString().slice(0, 10);
      exportService.downloadBlob(blob, `conversas-${dateStamp}.${format}`);
      toast.success('Exporta??o conclu?da!');
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsExporting(false);
    }
  };

  const statusTabs = [
    { value: null, label: 'Todas', count: conversations.length },
    ...Object.entries(CONVERSATION_STATUS_CONFIG).map(([key, config]) => ({
      value: key,
      label: config.label,
      count: statusCounts[key] || 0,
    })),
  ];

  const columns = [
    {
      key: 'contact',
      header: 'Contato',
      render: (conv: Conversation) => (
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center">
            <UserIcon className="w-5 h-5 text-primary-600" />
          </div>
          <div>
            <p className="font-semibold text-gray-900 dark:text-white">{conv.contact_name || 'Sem nome'}</p>
            <p className="text-sm text-gray-500 dark:text-zinc-400">{conv.phone_number}</p>
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (conv: Conversation) => (
        <div className="flex flex-col gap-1">
          <ConversationStatusBadge status={conv.status} />
          <ConversationModeBadge mode={conv.mode} />
        </div>
      ),
    },
    {
      key: 'orders',
      header: 'Pedidos',
      render: (conv: Conversation) => {
        const summary = getOrderSummary(conv.id);
        if (!summary) {
          return <span className="text-sm text-gray-400">Sem pedidos</span>;
        }
        return (
          <div className="flex flex-wrap gap-1">
            {summary.pending > 0 && (
              <span className="px-2 py-0.5 bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300 text-xs rounded-full">
                {summary.pending} pendente(s)
              </span>
            )}
            {summary.paid > 0 && (
              <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 text-xs rounded-full">
                {summary.paid} pago(s)
              </span>
            )}
            {summary.shipped > 0 && (
              <span className="px-2 py-0.5 bg-teal-100 text-teal-700 text-xs rounded-full">
                {summary.shipped} enviado(s)
              </span>
            )}
            {summary.delivered > 0 && (
              <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 text-xs rounded-full">
                {summary.delivered} entregue(s)
              </span>
            )}
          </div>
        );
      },
    },
    {
      key: 'tags',
      header: 'Tags',
      render: (conv: Conversation) => (
        <div className="flex flex-wrap gap-1">
          {conv.tags.length === 0 ? (
            <span className="text-sm text-gray-400">-</span>
          ) : (
            <>
              {conv.tags.slice(0, 3).map((tag) => (
                <span key={tag} className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400 text-xs rounded-full">
                  {tag}
                </span>
              ))}
              {conv.tags.length > 3 && (
                <span className="text-xs text-gray-400">+{conv.tags.length - 3}</span>
              )}
            </>
          )}
        </div>
      ),
    },
    {
      key: 'last_message_at',
      header: 'Última Atividade',
      render: (conv: Conversation) => (
        <div className="flex items-center gap-2">
          <ClockIcon className="w-4 h-4 text-gray-400" />
          <span className="text-sm text-gray-600 dark:text-zinc-400">
            {conv.last_message_at
              ? formatDistanceToNow(new Date(conv.last_message_at), { addSuffix: true, locale: ptBR })
              : '-'}
          </span>
        </div>
      ),
    },
    {
      key: 'actions',
      header: 'Ações',
      render: (conv: Conversation) => (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={conv.mode === 'human' ? 'secondary' : 'primary'}
            leftIcon={conv.mode === 'human' ? <CpuChipIcon className="w-4 h-4" /> : <UserIcon className="w-4 h-4" />}
            onClick={(e) => {
              e.stopPropagation();
              handleSwitchMode(conv, conv.mode === 'human' ? 'auto' : 'human');
            }}
          >
            {conv.mode === 'human' ? 'Auto' : 'Humano'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              loadNotes(conv);
            }}
          >
            Notas
          </Button>
          {conv.status === 'open' || conv.status === 'pending' ? (
            <>
              <Button
                size="sm"
                variant="ghost"
                leftIcon={<CheckCircleIcon className="w-4 h-4" />}
                onClick={(e) => {
                  e.stopPropagation();
                  handleResolveConversation(conv);
                }}
              >
                Resolver
              </Button>
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<XCircleIcon className="w-4 h-4" />}
                onClick={(e) => {
                  e.stopPropagation();
                  handleCloseConversation(conv);
                }}
              >
                Fechar
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              leftIcon={<ArrowPathIcon className="w-4 h-4" />}
              onClick={(e) => {
                e.stopPropagation();
                handleReopenConversation(conv);
              }}
            >
              Reabrir
            </Button>
          )}
        </div>
      ),
    },
  ];

  if (isLoading) {
    return <PageLoading />;
  }

  return (
    <div className="p-6 space-y-6">
      <PageTitle
        title="Conversas"
        subtitle={`${filteredConversations.length} de ${conversations.length} conversa(s)`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={() => handleExport('csv')}
              isLoading={isExporting}
            >
              Exportar CSV
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleExport('xlsx')}
              isLoading={isExporting}
            >
              Exportar XLSX
            </Button>
          </div>
        }
      />

        {/* Status Tabs */}
        <StatusTabs
          tabs={statusTabs}
          value={statusFilter}
          onChange={setStatusFilter}
        />

        {/* Search and Mode Filter */}
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="relative flex-1">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              placeholder="Buscar por nome, telefone ou tag..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>
          <div className="flex gap-2">
            {Object.entries(CONVERSATION_MODE_CONFIG).map(([key, config]) => (
              <button
                key={key}
                onClick={() => setModeFilter(modeFilter === key ? null : key)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                  modeFilter === key
                    ? 'bg-gray-900 text-white'
                    : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50'
                }`}
              >
                {key === 'auto' && <CpuChipIcon className="w-4 h-4" />}
                {key === 'human' && <UserIcon className="w-4 h-4" />}
                {key === 'hybrid' && <ChatBubbleLeftRightIcon className="w-4 h-4" />}
                {config.label}
                <span className={`px-1.5 py-0.5 rounded-full text-xs ${
                  modeFilter === key ? 'bg-white/20' : 'bg-gray-100'
                }`}>
                  {modeCounts[key] || 0}
                </span>
              </button>
            ))}
          </div>
          {(statusFilter || modeFilter || searchQuery) && (
            <Button
              variant="ghost"
              onClick={() => {
                setStatusFilter(null);
                setModeFilter(null);
                setSearchQuery('');
              }}
            >
              Limpar
            </Button>
          )}
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-lg">
                <ChatBubbleLeftRightIcon className="w-6 h-6 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{statusCounts.open || 0}</p>
                <p className="text-sm text-gray-600 dark:text-zinc-400">Abertas</p>
              </div>
            </div>
          </Card>
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-yellow-100 dark:bg-yellow-900/40 rounded-lg">
                <ClockIcon className="w-6 h-6 text-yellow-600 dark:text-yellow-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{statusCounts.pending || 0}</p>
                <p className="text-sm text-gray-600 dark:text-zinc-400">Pendentes</p>
              </div>
            </div>
          </Card>
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
                <CheckCircleIcon className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{statusCounts.resolved || 0}</p>
                <p className="text-sm text-gray-600 dark:text-zinc-400">Resolvidas</p>
              </div>
            </div>
          </Card>
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-100 dark:bg-purple-900/40 rounded-lg">
                <UserIcon className="w-6 h-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{modeCounts.human || 0}</p>
                <p className="text-sm text-gray-600 dark:text-zinc-400">Atendimento Humano</p>
              </div>
            </div>
          </Card>
        </div>

        {/* Conversations Table */}
        <Card noPadding>
          <Table
            columns={columns}
            data={filteredConversations}
            keyExtractor={(conv) => conv.id}
            onRowClick={(conv) => setDetailConversation(conv)}
            emptyMessage={
              statusFilter || modeFilter || searchQuery
                ? "Nenhuma conversa encontrada com os filtros aplicados"
                : "Nenhuma conversa encontrada"
            }
          />
        </Card>

      {/* Notes Modal */}
      <Modal
        isOpen={!!selectedConversation}
        onClose={() => setSelectedConversation(null)}
        title={`Notas - ${selectedConversation?.contact_name || selectedConversation?.phone_number}`}
        size="md"
      >
        <div className="space-y-4">
          <div>
            <Textarea
              placeholder="Adicionar uma nota..."
              rows={3}
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
            />
            <div className="flex justify-end mt-2">
              <Button size="sm" onClick={handleAddNote} isLoading={isAddingNote}>
                Adicionar Nota
              </Button>
            </div>
          </div>

          <div className="border-t pt-4 space-y-3 max-h-96 overflow-y-auto">
            {notes.length === 0 ? (
              <p className="text-center text-gray-500 dark:text-zinc-400 py-4">Nenhuma nota</p>
            ) : (
              notes.map((note) => (
                <div key={note.id} className="bg-gray-50 dark:bg-black rounded-lg p-3">
                  <p className="text-sm text-gray-900 dark:text-white">{note.content}</p>
                  <p className="text-xs text-gray-500 dark:text-zinc-400 mt-2">
                    {format(new Date(note.created_at), "dd/MM/yyyy HH:mm", { locale: ptBR })}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </Modal>

      {/* Conversation Detail Modal */}
      <Modal
        isOpen={!!detailConversation}
        onClose={() => setDetailConversation(null)}
        title="Detalhes da Conversa"
        size="lg"
      >
        {detailConversation && (
          <div className="space-y-6">
            {/* Contact Info */}
            <div className="flex items-center gap-4 p-4 bg-gray-50 dark:bg-black rounded-lg">
              <div className="w-16 h-16 rounded-full bg-primary-100 flex items-center justify-center">
                <UserIcon className="w-8 h-8 text-primary-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {detailConversation.contact_name || 'Sem nome'}
                </h3>
                <p className="text-gray-600 dark:text-zinc-400">{detailConversation.phone_number}</p>
              </div>
              <div className="flex flex-col gap-2">
                <ConversationStatusBadge status={detailConversation.status} size="md" />
                <ConversationModeBadge mode={detailConversation.mode} size="md" />
              </div>
            </div>

            {/* Tags */}
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2 flex items-center gap-2">
                <TagIcon className="w-4 h-4" />
                Tags
              </h4>
              <div className="flex flex-wrap gap-2">
                {detailConversation.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-3 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-zinc-300 text-sm rounded-full flex items-center gap-2"
                  >
                    {tag}
                    <button
                      onClick={() => handleRemoveTag(tag)}
                      className="text-gray-400 hover:text-red-500"
                    >
                      <XCircleIcon className="w-4 h-4" />
                    </button>
                  </span>
                ))}
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="Nova tag..."
                    value={newTag}
                    onChange={(e) => setNewTag(e.target.value)}
                    className="w-32"
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    leftIcon={<PlusIcon className="w-4 h-4" />}
                    onClick={handleAddTag}
                    isLoading={isAddingTag}
                    disabled={!newTag.trim()}
                  >
                    Adicionar
                  </Button>
                </div>
              </div>
            </div>

            {/* Orders Summary */}
            {conversationOrders[detailConversation.id] && (
              <div>
                <h4 className="text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">Pedidos do Cliente</h4>
                <div className="space-y-2">
                  {conversationOrders[detailConversation.id].map((order) => (
                    <div
                      key={order.id}
                      className="flex items-center justify-between p-3 bg-gray-50 dark:bg-black rounded-lg"
                    >
                      <div>
                        <p className="font-medium text-gray-900 dark:text-white">#{order.order_number}</p>
                        <p className="text-sm text-gray-500 dark:text-zinc-400">
                          {format(new Date(order.created_at), "dd/MM/yyyy", { locale: ptBR })}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold text-gray-900 dark:text-white">
                          R$ {order.total.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                        </p>
                        <span className={`px-2 py-0.5 text-xs rounded-full ${
                          order.status === 'paid' ? 'bg-green-100 text-green-700' :
                          order.status === 'shipped' ? 'bg-teal-100 text-teal-700' :
                          order.status === 'delivered' ? 'bg-indigo-100 text-indigo-700' :
                          order.status === 'cancelled' ? 'bg-red-100 text-red-700' :
                          'bg-yellow-100 text-yellow-700'
                        }`}>
                          {order.status === 'pending' ? 'Pendente' :
                          order.status === 'processing' ? 'Processando Pagamento' :
                          order.status === 'paid' ? 'Pago' :
                           order.status === 'shipped' ? 'Enviado' :
                           order.status === 'delivered' ? 'Entregue' :
                           order.status === 'cancelled' ? 'Cancelado' :
                           order.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Timestamps */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-gray-500 dark:text-zinc-400">Criada em</p>
                <p className="font-medium text-gray-900 dark:text-white">
                  {format(new Date(detailConversation.created_at), "dd/MM/yyyy HH:mm", { locale: ptBR })}
                </p>
              </div>
              <div>
                <p className="text-gray-500 dark:text-zinc-400">Última mensagem</p>
                <p className="font-medium text-gray-900 dark:text-white">
                  {detailConversation.last_message_at
                    ? format(new Date(detailConversation.last_message_at), "dd/MM/yyyy HH:mm", { locale: ptBR })
                    : '-'}
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-4 border-t">
              <Button
                variant={detailConversation.mode === 'human' ? 'secondary' : 'primary'}
                leftIcon={detailConversation.mode === 'human' ? <CpuChipIcon className="w-4 h-4" /> : <UserIcon className="w-4 h-4" />}
                onClick={() => {
                  handleSwitchMode(detailConversation, detailConversation.mode === 'human' ? 'auto' : 'human');
                  setDetailConversation(null);
                }}
              >
                Mudar para {detailConversation.mode === 'human' ? 'Automático' : 'Humano'}
              </Button>
              {detailConversation.status === 'open' || detailConversation.status === 'pending' ? (
                <>
                  <Button
                    variant="secondary"
                    leftIcon={<CheckCircleIcon className="w-4 h-4" />}
                    onClick={() => {
                      handleResolveConversation(detailConversation);
                      setDetailConversation(null);
                    }}
                  >
                    Resolver
                  </Button>
                  <Button
                    variant="danger"
                    leftIcon={<XCircleIcon className="w-4 h-4" />}
                    onClick={() => {
                      handleCloseConversation(detailConversation);
                      setDetailConversation(null);
                    }}
                  >
                    Fechar
                  </Button>
                </>
              ) : (
                <Button
                  variant="primary"
                  leftIcon={<ArrowPathIcon className="w-4 h-4" />}
                  onClick={() => {
                    handleReopenConversation(detailConversation);
                    setDetailConversation(null);
                  }}
                >
                  Reabrir
                </Button>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};
