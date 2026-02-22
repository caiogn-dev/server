/**
 * Payments Page - Shows payment information from store orders
 * Uses the unified stores API to fetch orders with payment data
 */
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import toast from 'react-hot-toast';
import {
  CurrencyDollarIcon,
  CheckCircleIcon,
  ClockIcon,
  XCircleIcon,
  ArrowPathIcon,
  BanknotesIcon,
  CreditCardIcon,
  QrCodeIcon,
  LinkIcon,
  ClipboardIcon,
} from '@heroicons/react/24/outline';
import {
  Card,
  Button,
  Table,
  PageLoading,
  StatusFilter,
  PageTitle,
} from '../../components/common';
import { ordersService } from '../../services';
import { Order } from '../../types';
import logger from '../../services/logger';
import { useStore } from '../../hooks';

// Payment status options based on StoreOrder.PaymentStatus
const PAYMENT_STATUS_OPTIONS = [
  { value: 'pending', label: 'Aguardando', color: 'warning' },
  { value: 'processing', label: 'Processando', color: 'purple' },
  { value: 'paid', label: 'Pago', color: 'success' },
  { value: 'failed', label: 'Falhou', color: 'danger' },
  { value: 'refunded', label: 'Reembolsado', color: 'gray' },
  { value: 'partially_refunded', label: 'Reembolso Parcial', color: 'orange' },
];

// Payment method display names
const PAYMENT_METHOD_LABELS: Record<string, { label: string; icon: React.ReactNode }> = {
  pix: { label: 'PIX', icon: <QrCodeIcon className="w-4 h-4" /> },
  credit_card: { label: 'Crédito', icon: <CreditCardIcon className="w-4 h-4" /> },
  debit_card: { label: 'Débito', icon: <CreditCardIcon className="w-4 h-4" /> },
  cash: { label: 'Dinheiro', icon: <BanknotesIcon className="w-4 h-4" /> },
  card: { label: 'Cartão', icon: <CreditCardIcon className="w-4 h-4" /> },
  mercadopago: { label: 'Mercado Pago', icon: <CurrencyDollarIcon className="w-4 h-4" /> },
};

// Payment status badge component
const PaymentStatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const config: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
    pending: { bg: 'bg-amber-100 dark:bg-amber-900/40 dark:bg-amber-900/40', text: 'text-amber-800 dark:text-amber-300', icon: <ClockIcon className="w-4 h-4" /> },
    processing: { bg: 'bg-purple-100 dark:bg-purple-900/40 dark:bg-purple-900/40', text: 'text-purple-800 dark:text-purple-300', icon: <ArrowPathIcon className="w-4 h-4 animate-spin" /> },
    paid: { bg: 'bg-green-100 dark:bg-green-900/40 dark:bg-green-900/40', text: 'text-green-800 dark:text-green-300', icon: <CheckCircleIcon className="w-4 h-4" /> },
    failed: { bg: 'bg-red-100 dark:bg-red-900/40 dark:bg-red-900/40', text: 'text-red-800 dark:text-red-300', icon: <XCircleIcon className="w-4 h-4" /> },
    refunded: { bg: 'bg-gray-100 dark:bg-gray-700 dark:bg-gray-700', text: 'text-gray-800 dark:text-gray-200 dark:text-zinc-300', icon: <ArrowPathIcon className="w-4 h-4" /> },
    partially_refunded: { bg: 'bg-orange-100 dark:bg-orange-900/40 dark:bg-orange-900/40', text: 'text-orange-800 dark:text-orange-300', icon: <ArrowPathIcon className="w-4 h-4" /> },
  };
  
  const { bg, text, icon } = config[status] || config.pending;
  const label = PAYMENT_STATUS_OPTIONS.find(o => o.value === status)?.label || status;
  
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${bg} ${text}`}>
      {icon}
      {label}
    </span>
  );
};

export const PaymentsPage: React.FC = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const { storeId: routeStoreId } = useParams<{ storeId?: string }>();
  const { storeSlug, stores } = useStore();
  const effectiveStoreSlug = useMemo(() => {
    if (!routeStoreId) return storeSlug || null;
    const match = stores.find((store) => store.id === routeStoreId || store.slug === routeStoreId);
    return match?.slug || match?.id || routeStoreId;
  }, [routeStoreId, storeSlug, stores]);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      // Get all orders from store, ordered by most recent
      const params: Record<string, string> = { ordering: '-created_at' };
      if (effectiveStoreSlug) params.store = effectiveStoreSlug;
      const ordersData = await ordersService.getOrders(params);
      setOrders(ordersData.results);
    } catch (error) {
      logger.error('Error loading payments:', error);
      toast.error('Erro ao carregar pagamentos');
    } finally {
      setIsLoading(false);
    }
  }, [effectiveStoreSlug]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle confirm payment (mark as paid)
  const handleConfirmPayment = async (order: Order) => {
    try {
      const updatedOrder = await ordersService.markPaid(order.id);
      setOrders(orders.map(o =>
        o.id === order.id
          ? { ...o, payment_status: updatedOrder.payment_status, status: updatedOrder.status }
          : o
      ));
      toast.success(`Pagamento do pedido #${order.order_number} confirmado!`);
    } catch (error) {
      logger.error('Error confirming payment:', error);
      toast.error('Erro ao confirmar pagamento');
    }
  };

  // Calculate stats
  const stats = useMemo(() => {
    const totalRevenue = orders
      .filter(o => o.payment_status === 'paid')
      .reduce((sum, o) => sum + Number(o.total || 0), 0);
    
    const pendingAmount = orders
      .filter(o => o.payment_status === 'pending')
      .reduce((sum, o) => sum + Number(o.total || 0), 0);
    
    const todayOrders = orders.filter(o => {
      const orderDate = new Date(o.created_at);
      const today = new Date();
      return orderDate.toDateString() === today.toDateString();
    });
    
    const todayRevenue = todayOrders
      .filter(o => o.payment_status === 'paid')
      .reduce((sum, o) => sum + Number(o.total || 0), 0);
    
    return {
      totalRevenue,
      pendingAmount,
      todayRevenue,
      todayCount: todayOrders.length,
      paidCount: orders.filter(o => o.payment_status === 'paid').length,
      pendingCount: orders.filter(o => o.payment_status === 'pending').length,
    };
  }, [orders]);

  // Count by payment status
  const paymentStatusCounts = useMemo(() => {
    return orders.reduce<Record<string, number>>((acc, order) => {
      const status = order.payment_status || 'pending';
      acc[status] = (acc[status] || 0) + 1;
      return acc;
    }, {});
  }, [orders]);

  // Filter orders by payment status
  const filteredOrders = useMemo(() => {
    if (!statusFilter) return orders;
    return orders.filter(order => order.payment_status === statusFilter);
  }, [orders, statusFilter]);

  // Filter options with counts
  const filterOptions = useMemo(() => {
    return PAYMENT_STATUS_OPTIONS.map(option => ({
      ...option,
      count: paymentStatusCounts[option.value] || 0,
    }));
  }, [paymentStatusCounts]);

  // Format currency
  const formatMoney = (value: number | string) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return `R$ ${num.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  // Table columns
  const columns = [
    {
      key: 'order_number',
      header: 'Pedido',
      render: (order: Order) => (
        <div>
          <span className="font-semibold text-gray-900 dark:text-white">#{order.order_number}</span>
          <p className="text-xs text-gray-500 dark:text-zinc-400">{order.customer_name}</p>
        </div>
      ),
    },
    {
      key: 'total',
      header: 'Valor',
      render: (order: Order) => (
        <span className="font-semibold text-gray-900 dark:text-white">{formatMoney(order.total)}</span>
      ),
    },
    {
      key: 'payment_method',
      header: 'Método',
      render: (order: Order) => {
        const method = order.payment_method || 'pix';
        const methodInfo = PAYMENT_METHOD_LABELS[method] || { label: method, icon: <CurrencyDollarIcon className="w-4 h-4" /> };
        return (
          <span className="inline-flex items-center gap-1.5 text-sm text-gray-700 dark:text-zinc-300">
            {methodInfo.icon}
            {methodInfo.label}
          </span>
        );
      },
    },
    {
      key: 'payment_status',
      header: 'Status',
      render: (order: Order) => (
        <PaymentStatusBadge status={order.payment_status || 'pending'} />
      ),
    },
    {
      key: 'payment_link',
      header: 'Link Pagamento',
      render: (order: Order) => {
        const { payment_method, pix_code, access_token, pix_ticket_url, payment_url, payment_link, init_point, payment_preference_id } = order;
        
        // Check for direct payment link (for card payments)
        const directLink = payment_url || payment_link || init_point;
        
        // Generate link from payment_preference_id if available (for card payments)
        const preferenceLink = payment_preference_id 
          ? `https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=${payment_preference_id}`
          : null;
        
        // SECURE: Generate link using access_token (not order_number)
        // This prevents unauthorized access to order details
        const clientPaymentLink = pix_code && access_token
          ? `https://pastita.com.br/pendente?token=${access_token}`
          : null;
        
        // Priority: pix_ticket_url > client payment page (with token) > direct link > preference link
        const finalPaymentLink = pix_ticket_url || clientPaymentLink || directLink || preferenceLink;
        
        // Show link if available
        if (finalPaymentLink) {
          return (
            <div className="flex items-center gap-2">
              <a
                href={finalPaymentLink}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-sm text-blue-700 dark:text-blue-300 bg-blue-50 hover:bg-blue-100 dark:bg-blue-900/40 rounded-lg font-medium transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <LinkIcon className="w-4 h-4" />
                Abrir
              </a>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  navigator.clipboard.writeText(finalPaymentLink);
                  toast.success('Link copiado! Envie para o cliente.');
                }}
                className="p-1.5 text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-300 dark:hover:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-700 dark:bg-gray-700 rounded"
                title="Copiar link"
              >
                <ClipboardIcon className="w-4 h-4" />
              </button>
            </div>
          );
        }
        
        // If payment method is cash, no link needed
        if (payment_method === 'cash') {
          return <span className="text-sm text-gray-500 dark:text-zinc-400">💵 Dinheiro</span>;
        }
        
        // No payment info yet
        return <span className="text-sm text-gray-400">-</span>;
      },
    },
    {
      key: 'created_at',
      header: 'Data',
      render: (order: Order) => (
        <div className="text-sm">
          <p className="text-gray-900 dark:text-white">{format(new Date(order.created_at), "dd/MM/yyyy", { locale: ptBR })}</p>
          <p className="text-gray-500 dark:text-zinc-400">{format(new Date(order.created_at), "HH:mm", { locale: ptBR })}</p>
        </div>
      ),
    },
    {
      key: 'actions',
      header: 'Ações',
      render: (order: Order) => (
        <div className="flex items-center gap-2">
          {order.payment_status === 'pending' && (
            <Button
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                handleConfirmPayment(order);
              }}
            >
              <CheckCircleIcon className="w-4 h-4 mr-1" />
              Confirmar
            </Button>
          )}
          {order.payment_status === 'paid' && (
            <span className="text-sm text-green-600 dark:text-green-400 font-medium">✓ Pago</span>
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
        title="Pagamentos"
        subtitle={`${orders.length} pedido(s) | ${formatMoney(stats.totalRevenue)} recebido`}
      />

        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 dark:bg-green-900/40 dark:bg-green-900/40 rounded-lg">
                <CurrencyDollarIcon className="w-6 h-6 text-green-600 dark:text-green-400 dark:text-green-400" />
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-zinc-400 dark:text-zinc-400">Receita Hoje</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white dark:text-white">{formatMoney(stats.todayRevenue)}</p>
                <p className="text-xs text-gray-500 dark:text-zinc-400 dark:text-zinc-400">{stats.todayCount} pedido(s)</p>
              </div>
            </div>
          </Card>
          
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/40 dark:bg-blue-900/40 rounded-lg">
                <CheckCircleIcon className="w-6 h-6 text-blue-600 dark:text-blue-400 dark:text-blue-400" />
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-zinc-400 dark:text-zinc-400">Total Recebido</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white dark:text-white">{formatMoney(stats.totalRevenue)}</p>
                <p className="text-xs text-gray-500 dark:text-zinc-400 dark:text-zinc-400">{stats.paidCount} pago(s)</p>
              </div>
            </div>
          </Card>
          
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-100 dark:bg-amber-900/40 dark:bg-amber-900/40 rounded-lg">
                <ClockIcon className="w-6 h-6 text-amber-600 dark:text-amber-400 dark:text-amber-400" />
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-zinc-400 dark:text-zinc-400">Aguardando</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white dark:text-white">{formatMoney(stats.pendingAmount)}</p>
                <p className="text-xs text-gray-500 dark:text-zinc-400 dark:text-zinc-400">{stats.pendingCount} pendente(s)</p>
              </div>
            </div>
          </Card>
          
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-100 dark:bg-purple-900/40 dark:bg-purple-900/40 rounded-lg">
                <BanknotesIcon className="w-6 h-6 text-purple-600 dark:text-purple-400 dark:text-purple-400" />
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-zinc-400 dark:text-zinc-400">Total Pedidos</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white dark:text-white">{orders.length}</p>
                <p className="text-xs text-gray-500 dark:text-zinc-400 dark:text-zinc-400">todos os tempos</p>
              </div>
            </div>
          </Card>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <StatusFilter
            options={filterOptions}
            value={statusFilter}
            onChange={setStatusFilter}
            className="flex-wrap"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={loadData}
          >
            <ArrowPathIcon className="w-4 h-4 mr-1" />
            Atualizar
          </Button>
        </div>

        {/* Payments Table */}
        <Card noPadding>
          <Table
            columns={columns}
            data={filteredOrders}
            keyExtractor={(order) => order.id}
            emptyMessage="Nenhum pagamento encontrado"
          />
        </Card>
    </div>
  );
};

export default PaymentsPage;
