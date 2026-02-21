import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { 
  MagnifyingGlassIcon, 
  TruckIcon, 
  CreditCardIcon, 
  XMarkIcon,
  Squares2X2Icon,
  ListBulletIcon,
  FunnelIcon,
  ArrowPathIcon,
  SignalIcon,
  SignalSlashIcon,
} from '@heroicons/react/24/outline';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import toast from 'react-hot-toast';
import { 
  Card, 
  Button, 
  Table, 
  OrderStatusBadge, 
  Modal, 
  Input, 
  Select, 
  PageLoading,
  OrderStatusTabs,
  PageTitle,
} from '../../components/common';
import { OrdersKanban, ORDER_STATUSES } from '../../components/orders/OrdersKanban';
import { exportService, getErrorMessage, ordersService } from '../../services';
import { useStore, useOrdersWebSocket, useNotificationSound } from '../../hooks';
import { Order } from '../../types';

type ViewMode = 'kanban' | 'table';
type OrderStatus = Order['status'];
type PaymentStatus = NonNullable<Order['payment_status']>;

const ORDER_STATUS_VALUES: OrderStatus[] = [
  'pending',
  'processing',
  'confirmed',
  'paid',
  'preparing',
  'ready',
  'shipped',
  'out_for_delivery',
  'delivered',
  'completed',
  'cancelled',
  'refunded',
  'failed',
];

const isOrderStatus = (value: unknown): value is OrderStatus => {
  return ORDER_STATUS_VALUES.includes(String(value) as OrderStatus);
};

const isPaymentStatus = (value: unknown): value is PaymentStatus => {
  return ['pending', 'processing', 'paid', 'failed', 'refunded', 'partially_refunded'].includes(String(value));
};

const toNumber = (value: unknown): number | undefined => {
  if (value === null || value === undefined) return undefined;
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && value.trim() !== '') return Number(value);
  return undefined;
};

const sanitizeOrderUpdate = (data: Record<string, unknown>): Partial<Order> => {
  const update: Partial<Order> = {};
  if (typeof data.order_number === 'string') update.order_number = data.order_number;
  if (isOrderStatus(data.status)) update.status = data.status;
  if (isPaymentStatus(data.payment_status)) update.payment_status = data.payment_status;
  const total = toNumber(data.total);
  if (total !== undefined) update.total = total;
  const subtotal = toNumber(data.subtotal);
  if (subtotal !== undefined) update.subtotal = subtotal;
  const discount = toNumber(data.discount);
  if (discount !== undefined) update.discount = discount;
  const deliveryFee = toNumber(data.delivery_fee);
  if (deliveryFee !== undefined) update.delivery_fee = deliveryFee;
  const tax = toNumber(data.tax);
  if (tax !== undefined) update.tax = tax;
  return update;
};

const formatMoney = (value: number | string | null | undefined) => {
  const num = typeof value === 'string' ? Number(value) : value ?? 0;
  return num.toLocaleString('pt-BR', { minimumFractionDigits: 2 });
};

export const OrdersPage: React.FC = () => {
  const navigate = useNavigate();
  const { storeId: routeStoreId } = useParams<{ storeId?: string }>();
  const { storeId: contextStoreId, storeSlug, storeName, stores } = useStore();
  
  // Use route storeId if available, otherwise use context
  const effectiveStoreId = routeStoreId || storeSlug || contextStoreId;
  const effectiveStoreSlug = useMemo(() => {
    if (!routeStoreId) return storeSlug || contextStoreId || null;
    const match = stores.find((store) => store.id === routeStoreId || store.slug === routeStoreId);
    return match?.slug || match?.id || routeStoreId;
  }, [routeStoreId, storeSlug, contextStoreId, stores]);
  const storeRouteBase = effectiveStoreSlug || effectiveStoreId;
  const orderDetailRoute = useCallback((orderId: string) => {
    return storeRouteBase ? `/stores/${storeRouteBase}/orders/${orderId}` : '/stores';
  }, [storeRouteBase]);
  
  // State
  const [orders, setOrders] = useState<Order[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isExporting, setIsExporting] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('kanban');
  const [showAllStatuses, setShowAllStatuses] = useState(false);
  
  // Modal states
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [actionModal, setActionModal] = useState<'ship' | 'payment' | 'cancel' | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  
  // Form states
  const [shipForm, setShipForm] = useState({ tracking_code: '', carrier: '' });
  const [paymentForm, setPaymentForm] = useState({ payment_reference: '' });
  const [cancelForm, setCancelForm] = useState({ reason: '' });
  
  // Load orders from unified API (defined first for use in WebSocket handlers)
  const loadOrders = useCallback(async () => {
    console.log('[Orders] loadOrders called with storeId:', effectiveStoreId);
    setIsLoading(true);
    try {
      const params: Record<string, string> = {};
      if (effectiveStoreSlug) params.store = effectiveStoreSlug;
      if (statusFilter) params.status = statusFilter;
      if (searchQuery) params.search = searchQuery;
      
      console.log('[Orders] Fetching orders with params:', params);
      const response = await ordersService.getOrders(params);
      console.log('[Orders] Received', response.results.length, 'orders');
      setOrders(response.results);
    } catch (error) {
      console.error('[Orders] Error loading orders:', error);
      toast.error(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }, [effectiveStoreId, effectiveStoreSlug, statusFilter, searchQuery]);

  // Notification sound
  const { playOrderSound, playSuccessSound, stopAlert, isAlertActive } = useNotificationSound({ enabled: true });

  // Debounced refresh - prevents rate limiting
  const refreshTimeout = useRef<number | undefined>(undefined);
  const lastRefresh = useRef<number>(0);

  const scheduleRefresh = useCallback(() => {
    const now = Date.now();
    // Don't refresh more than once every 3 seconds
    if (now - lastRefresh.current < 3000) {
      console.log('[Orders] Skipping refresh - too soon');
      return;
    }
    
    if (refreshTimeout.current) {
      window.clearTimeout(refreshTimeout.current);
    }
    
    refreshTimeout.current = window.setTimeout(() => {
      lastRefresh.current = Date.now();
      loadOrders();
    }, 1000);
  }, [loadOrders]);

  // Real-time WebSocket connection
  const { isConnected, connectionError } = useOrdersWebSocket({
    onOrderCreated: (data) => {
      console.log('[Orders] New order received:', data);
      playOrderSound();
      toast.success(`🎉 Novo pedido #${data.order_number || data.order_id?.toString().slice(0, 8)}!`, {
        duration: 6000,
        icon: '🛒',
      });
      // Force immediate refresh for new orders (bypass debounce)
      lastRefresh.current = 0;
      loadOrders();
    },
    onOrderUpdated: (data) => {
      console.log('[Orders] Order updated:', data);
      // Update order in state without full reload
      const update = sanitizeOrderUpdate(data as Record<string, unknown>);
      setOrders(prev => prev.map(o =>
        o.id === data.order_id ? { ...o, ...update } : o
      ));
    },
    onStatusChanged: (data) => {
      console.log('[Orders] Status changed:', data);
      toast(`📦 Pedido #${data.order_number} → ${data.status}`, { duration: 4000 });
      // Update order status in state
      const nextStatus = isOrderStatus(data.status) ? data.status : undefined;
      setOrders(prev => prev.map(o =>
        o.id === data.order_id ? { ...o, status: nextStatus || o.status } : o
      ));
    },
    onPaymentReceived: (data) => {
      console.log('[Orders] Payment received:', data);
      playSuccessSound();
      toast.success(`💰 Pagamento confirmado - #${data.order_number || data.order_id?.toString().slice(0, 8)}!`, {
        duration: 6000,
      });
      // Update payment status in state
      setOrders(prev => prev.map(o => 
        o.id === data.order_id ? { ...o, payment_status: 'paid' } : o
      ));
    },
    enabled: true,
  });

  // Stop alert when user interacts with the page
  useEffect(() => {
    if (isAlertActive) {
      const stopOnInteraction = () => stopAlert();
      document.addEventListener('click', stopOnInteraction, { once: true });
      return () => document.removeEventListener('click', stopOnInteraction);
    }
  }, [isAlertActive, stopAlert]);

  // Initial load only
  useEffect(() => {
    loadOrders();
    // Cleanup timeout on unmount
    return () => {
      if (refreshTimeout.current) {
        window.clearTimeout(refreshTimeout.current);
      }
    };
  }, [loadOrders]);

  // Handle status change from Kanban drag-and-drop (optimistic update handled by Kanban)
  const handleKanbanStatusChange = async (orderId: string, newStatus: OrderStatus) => {
    // Map status to API action
    switch (newStatus) {
      case 'confirmed':
        await ordersService.confirmOrder(orderId);
        break;
      case 'processing':
        await ordersService.startProcessing(orderId);
        break;
      case 'preparing':
        await ordersService.startPreparing(orderId);
        break;
      case 'ready':
        await ordersService.markReady(orderId);
        break;
      case 'out_for_delivery':
        await ordersService.markOutForDelivery(orderId);
        break;
      case 'delivered':
        await ordersService.deliverOrder(orderId);
        break;
      case 'cancelled':
        await ordersService.cancelOrder(orderId, 'Cancelado via Kanban');
        break;
      default:
        throw new Error(`Status não suportado: ${newStatus}`);
    }
    toast.success('Status atualizado!');
    // Note: No loadOrders() here - Kanban handles optimistic updates
  };

  // Calculate status counts
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    orders.forEach((order) => {
      counts[order.status] = (counts[order.status] || 0) + 1;
    });
    return counts;
  }, [orders]);

  // Filter orders (client-side for search)
  const filteredOrders = useMemo(() => {
    if (!searchQuery) return orders;
    
    const query = searchQuery.toLowerCase();
    return orders.filter((order) =>
      order.order_number.toLowerCase().includes(query) ||
      order.customer_name?.toLowerCase().includes(query) ||
      order.customer_phone?.includes(query) ||
      order.customer_email?.toLowerCase().includes(query)
    );
  }, [orders, searchQuery]);

  // Export orders
  const handleExport = async (format: 'csv' | 'xlsx') => {
    setIsExporting(true);
    try {
      const blob = await exportService.exportOrders({
        format,
        status: statusFilter || undefined,
        store: effectiveStoreSlug || undefined,
      });
      const dateStamp = new Date().toISOString().slice(0, 10);
      exportService.downloadBlob(blob, `pedidos-${dateStamp}.${format}`);
      toast.success('Exportação concluída!');
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsExporting(false);
    }
  };

  // Get available actions for an order
  const getOrderActions = (order: Order) => {
    const actions: Array<{ 
      action: string; 
      label: string; 
      variant?: 'primary' | 'secondary' | 'danger'; 
      icon?: React.ReactNode 
    }> = [];
    
    const status = order.status.toLowerCase();
    
    switch (status) {
      case 'pending':
      case 'pendente':
        actions.push({ action: 'confirm', label: 'Confirmar', variant: 'primary' });
        break;
      case 'processing':
        actions.push({ action: 'mark_paid', label: 'Confirmar Pagamento', variant: 'primary', icon: <CreditCardIcon className="w-4 h-4" /> });
        break;
      case 'confirmed':
      case 'confirmado':
      case 'aprovado':
      case 'paid':
        actions.push({ action: 'prepare', label: 'Preparar', variant: 'primary' });
        break;
      case 'preparing':
      case 'preparando':
        actions.push({ action: 'ship', label: 'Enviar', variant: 'primary', icon: <TruckIcon className="w-4 h-4" /> });
        break;
      case 'shipped':
      case 'enviado':
      case 'out_for_delivery':
        actions.push({ action: 'deliver', label: 'Entregar', variant: 'primary' });
        break;
    }
    
    // Cancel action for non-final statuses
    const finalStatuses = ['cancelled', 'cancelado', 'delivered', 'entregue', 'refunded', 'failed', 'completed'];
    if (!finalStatuses.includes(status)) {
      actions.push({ action: 'cancel', label: 'Cancelar', variant: 'danger', icon: <XMarkIcon className="w-4 h-4" /> });
    }
    
    return actions;
  };

  // Handle action click
  const handleAction = (order: Order, action: string) => {
    setSelectedOrder(order);
    
    switch (action) {
      case 'ship':
        setActionModal('ship');
        break;
      case 'mark_paid':
        setActionModal('payment');
        break;
      case 'cancel':
        setActionModal('cancel');
        break;
      default:
        handleStatusUpdate(order, action);
    }
  };

  // Update order status via API
  const handleStatusUpdate = async (order: Order, action: string) => {
    setIsUpdating(true);
    try {
      switch (action) {
        case 'confirm':
          await ordersService.confirmOrder(order.id);
          break;
        case 'prepare':
          await ordersService.startPreparing(order.id);
          break;
        case 'deliver':
          await ordersService.deliverOrder(order.id);
          break;
        default:
          throw new Error(`Ação desconhecida: ${action}`);
      }
      toast.success('Status atualizado!');
      await loadOrders();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsUpdating(false);
    }
  };

  // Handle ship form submit
  const handleShipSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrder) return;
    
    setIsUpdating(true);
    try {
      await ordersService.shipOrder(selectedOrder.id, shipForm.tracking_code, shipForm.carrier);
      toast.success('Pedido marcado como enviado!');
      setActionModal(null);
      setSelectedOrder(null);
      setShipForm({ tracking_code: '', carrier: '' });
      await loadOrders();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsUpdating(false);
    }
  };

  // Handle payment form submit
  const handlePaymentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrder) return;
    
    setIsUpdating(true);
    try {
      await ordersService.markPaid(selectedOrder.id, paymentForm.payment_reference);
      toast.success('Pagamento confirmado!');
      setActionModal(null);
      setSelectedOrder(null);
      setPaymentForm({ payment_reference: '' });
      await loadOrders();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsUpdating(false);
    }
  };

  // Handle cancel form submit
  const handleCancelSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrder) return;
    
    setIsUpdating(true);
    try {
      await ordersService.cancelOrder(selectedOrder.id, cancelForm.reason);
      toast.success('Pedido cancelado!');
      setActionModal(null);
      setSelectedOrder(null);
      setCancelForm({ reason: '' });
      await loadOrders();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsUpdating(false);
    }
  };

  // Table columns
  const columns = [
    {
      key: 'order_number',
      header: 'Pedido',
      render: (order: Order) => (
        <div>
          <p className="font-semibold text-gray-900 dark:text-white">#{order.order_number}</p>
          <p className="text-sm text-gray-500 dark:text-zinc-400">
            {format(new Date(order.created_at), "dd/MM/yyyy HH:mm", { locale: ptBR })}
          </p>
          {order.source && (
            <span className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400 rounded">
              {order.source}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'customer',
      header: 'Cliente',
      render: (order: Order) => (
        <div>
          <p className="font-medium text-gray-900 dark:text-white">{order.customer_name || '-'}</p>
          <p className="text-sm text-gray-500 dark:text-zinc-400">{order.customer_phone || '-'}</p>
        </div>
      ),
    },
    {
      key: 'items',
      header: 'Itens',
      render: (order: Order) => (
        <span className="text-sm font-medium text-gray-900 dark:text-white">
          {order.items_count ?? order.items?.length ?? 0} item(ns)
        </span>
      ),
    },
    {
      key: 'total',
      header: 'Total',
      render: (order: Order) => (
        <span className="font-semibold text-gray-900 dark:text-white">
          R$ {formatMoney(order.total)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (order: Order) => <OrderStatusBadge status={order.status} />,
    },
    {
      key: 'actions',
      header: 'Ações',
      render: (order: Order) => {
        const actions = getOrderActions(order);
        return (
          <div className="flex items-center gap-2">
            {actions.slice(0, 2).map((action) => (
              <Button
                key={action.action}
                size="sm"
                variant={action.variant || 'secondary'}
                leftIcon={action.icon}
                onClick={(e) => {
                  e.stopPropagation();
                  handleAction(order, action.action);
                }}
              >
                {action.label}
              </Button>
            ))}
          </div>
        );
      },
    },
  ];

  // Visible statuses for Kanban
  const visibleStatuses = useMemo(() => {
    if (showAllStatuses) {
      return ORDER_STATUSES.map(s => s.id);
    }
    // Default: show active statuses (full delivery flow including processing)
    return ['pending', 'processing', 'confirmed', 'preparing', 'ready', 'out_for_delivery', 'delivered'];
  }, [showAllStatuses]);

  if (isLoading) {
    return <PageLoading />;
  }

  return (
    <div className="h-full flex flex-col p-4 md:p-6">
      <PageTitle
        title="Pedidos"
        subtitle={`${filteredOrders.length} pedido(s)${storeName ? ` - ${storeName}` : ''}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/* WebSocket Connection Status */}
            <div 
              className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${
                isConnected 
                  ? 'bg-green-100 text-green-700' 
                  : 'bg-red-100 text-red-700'
              }`}
              title={isConnected ? 'Conectado - Atualizações em tempo real' : connectionError || 'Desconectado'}
            >
              {isConnected ? (
                <>
                  <SignalIcon className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Ao vivo</span>
                </>
              ) : (
                <>
                  <SignalSlashIcon className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Offline</span>
                </>
              )}
            </div>

            {/* Test Sound Button */}
            <button
              onClick={() => {
                console.log('[Test] Playing test sound...');
                playOrderSound();
              }}
              className="px-2 py-1 text-xs bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 rounded-full hover:bg-purple-200"
              title="Testar som de notificação"
            >
              🔊 Testar
            </button>

            {/* View Mode Toggle */}
            <div className="flex items-center bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
              <button
                onClick={() => setViewMode('kanban')}
                className={`p-1.5 rounded ${viewMode === 'kanban' ? 'bg-white dark:bg-gray-700 shadow-sm' : 'text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-300'}`}
                title="Visualização Kanban"
              >
                <Squares2X2Icon className="w-5 h-5" />
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`p-1.5 rounded ${viewMode === 'table' ? 'bg-white dark:bg-gray-700 shadow-sm' : 'text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-300'}`}
                title="Visualização em Lista"
              >
                <ListBulletIcon className="w-5 h-5" />
              </button>
            </div>

            {/* Refresh */}
            <Button
              variant="secondary"
              size="sm"
              onClick={loadOrders}
              title="Atualizar"
            >
              <ArrowPathIcon className="w-4 h-4" />
            </Button>

            {/* Show All Statuses (Kanban only) */}
            {viewMode === 'kanban' && (
              <Button
                variant={showAllStatuses ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setShowAllStatuses(!showAllStatuses)}
                title="Mostrar todos os status"
              >
                <FunnelIcon className="w-4 h-4" />
              </Button>
            )}

            {/* Export */}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleExport('csv')}
              isLoading={isExporting}
              className="hidden sm:inline-flex"
            >
              CSV
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleExport('xlsx')}
              isLoading={isExporting}
              className="hidden sm:inline-flex"
            >
              XLSX
            </Button>
          </div>
        }
      />

      <div className="flex-1 space-y-4 overflow-hidden">
        {/* Search Bar */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              placeholder="Buscar por número, cliente, telefone..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
          </div>
        </div>

        {/* Kanban View */}
        {viewMode === 'kanban' && (
          <div className="flex-1 overflow-hidden">
            <OrdersKanban
              orders={filteredOrders}
              onOrderClick={(order) => navigate(orderDetailRoute(order.id))}
              onStatusChange={handleKanbanStatusChange}
              visibleStatuses={visibleStatuses}
            />
          </div>
        )}

        {/* Table View */}
        {viewMode === 'table' && (
          <>
            {/* Status Tabs */}
            <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
              <OrderStatusTabs
                value={statusFilter}
                onChange={setStatusFilter}
                counts={statusCounts}
              />
            </div>

            {/* Orders Table */}
            <Card>
              {filteredOrders.length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-gray-500 dark:text-zinc-400">Nenhum pedido encontrado</p>
                </div>
              ) : (
                <Table
                  columns={columns}
                  data={filteredOrders}
                  keyExtractor={(order) => order.id}
                  onRowClick={(order) => navigate(orderDetailRoute(order.id))}
                />
              )}
            </Card>
          </>
        )}
      </div>

      {/* Ship Modal */}
      <Modal
        isOpen={actionModal === 'ship'}
        onClose={() => {
          setActionModal(null);
          setSelectedOrder(null);
        }}
        title="Enviar Pedido"
      >
        <form onSubmit={handleShipSubmit} className="space-y-4">
          <Input
            label="Código de Rastreio"
            value={shipForm.tracking_code}
            onChange={(e) => setShipForm({ ...shipForm, tracking_code: e.target.value })}
            placeholder="Ex: BR123456789BR"
          />
          <Input
            label="Transportadora"
            value={shipForm.carrier}
            onChange={(e) => setShipForm({ ...shipForm, carrier: e.target.value })}
            placeholder="Ex: Correios, Jadlog..."
          />
          <div className="flex justify-end gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setActionModal(null);
                setSelectedOrder(null);
              }}
            >
              Cancelar
            </Button>
            <Button type="submit" isLoading={isUpdating}>
              Confirmar Envio
            </Button>
          </div>
        </form>
      </Modal>

      {/* Payment Modal */}
      <Modal
        isOpen={actionModal === 'payment'}
        onClose={() => {
          setActionModal(null);
          setSelectedOrder(null);
        }}
        title="Confirmar Pagamento"
      >
        <form onSubmit={handlePaymentSubmit} className="space-y-4">
          <Input
            label="Referência do Pagamento"
            value={paymentForm.payment_reference}
            onChange={(e) => setPaymentForm({ ...paymentForm, payment_reference: e.target.value })}
            placeholder="Ex: PIX, Transferência..."
          />
          <div className="flex justify-end gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setActionModal(null);
                setSelectedOrder(null);
              }}
            >
              Cancelar
            </Button>
            <Button type="submit" isLoading={isUpdating}>
              Confirmar Pagamento
            </Button>
          </div>
        </form>
      </Modal>

      {/* Cancel Modal */}
      <Modal
        isOpen={actionModal === 'cancel'}
        onClose={() => {
          setActionModal(null);
          setSelectedOrder(null);
        }}
        title="Cancelar Pedido"
      >
        <form onSubmit={handleCancelSubmit} className="space-y-4">
          <Input
            label="Motivo do Cancelamento"
            value={cancelForm.reason}
            onChange={(e) => setCancelForm({ ...cancelForm, reason: e.target.value })}
            placeholder="Informe o motivo..."
            required
          />
          <div className="flex justify-end gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setActionModal(null);
                setSelectedOrder(null);
              }}
            >
              Voltar
            </Button>
            <Button type="submit" variant="danger" isLoading={isUpdating}>
              Confirmar Cancelamento
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default OrdersPage;
