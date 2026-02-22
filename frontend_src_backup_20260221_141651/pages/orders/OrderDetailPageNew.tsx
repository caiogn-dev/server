/**
 * Order Detail Page - Clean & Modern Design
 * 
 * Minimalist design focused on:
 * - Clear visual hierarchy
 * - Essential information only
 * - Intuitive actions
 * - Beautiful progress timeline
 */
import React, { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeftIcon,
  PhoneIcon,
  EnvelopeIcon,
  MapPinIcon,
  ClockIcon,
  CheckIcon,
  TruckIcon,
  HomeIcon,
  XMarkIcon,
  PrinterIcon,
  ChatBubbleLeftIcon,
} from '@heroicons/react/24/outline';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import toast from 'react-hot-toast';
import { Card, Button, Modal, PageLoading } from '../../components/common';
import { ordersService, paymentsService, getErrorMessage } from '../../services';
import { Order, Payment } from '../../types';
import { useOrderPrint } from '../../components/orders/OrderPrint';
import { useStore } from '../../hooks';

// =============================================================================
// STATUS CONFIGURATION
// =============================================================================

const STATUS_FLOW = [
  { id: 'pending', label: 'Pendente', icon: ClockIcon, color: 'yellow' },
  { id: 'confirmed', label: 'Confirmado', icon: CheckIcon, color: 'blue' },
  { id: 'preparing', label: 'Preparando', icon: ClockIcon, color: 'orange' },
  { id: 'ready', label: 'Pronto', icon: CheckIcon, color: 'purple' },
  { id: 'out_for_delivery', label: 'Em Entrega', icon: TruckIcon, color: 'indigo' },
  { id: 'delivered', label: 'Entregue', icon: HomeIcon, color: 'green' },
];

const STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  pending: { bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200' },
  confirmed: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
  paid: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
  preparing: { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' },
  processing: { bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' },
  ready: { bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200' },
  out_for_delivery: { bg: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-200' },
  shipped: { bg: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-200' },
  delivered: { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' },
  completed: { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' },
  cancelled: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
};

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendente',
  confirmed: 'Confirmado',
  paid: 'Pago',
  preparing: 'Preparando',
  processing: 'Processando',
  ready: 'Pronto',
  out_for_delivery: 'Em Entrega',
  shipped: 'Enviado',
  delivered: 'Entregue',
  completed: 'Concluído',
  cancelled: 'Cancelado',
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

const formatMoney = (value: number | undefined | null) => {
  return `R$ ${(value ?? 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
};

const getStatusIndex = (status: string): number => {
  const normalizedStatus = status.toLowerCase();
  const index = STATUS_FLOW.findIndex(s => 
    s.id === normalizedStatus || 
    (normalizedStatus === 'paid' && s.id === 'confirmed') ||
    (normalizedStatus === 'processing' && s.id === 'preparing') ||
    (normalizedStatus === 'shipped' && s.id === 'out_for_delivery') ||
    (normalizedStatus === 'completed' && s.id === 'delivered')
  );
  return index >= 0 ? index : 0;
};

// =============================================================================
// PROGRESS TIMELINE COMPONENT
// =============================================================================

interface ProgressTimelineProps {
  currentStatus: string;
  isCancelled?: boolean;
}

const ProgressTimeline: React.FC<ProgressTimelineProps> = ({ currentStatus, isCancelled }) => {
  const currentIndex = getStatusIndex(currentStatus);
  
  if (isCancelled) {
    return (
      <div className="flex items-center justify-center py-6">
        <div className="flex items-center gap-3 px-6 py-3 bg-red-50 rounded-full">
          <XMarkIcon className="w-6 h-6 text-red-500" />
          <span className="text-lg font-semibold text-red-700 dark:text-red-300">Pedido Cancelado</span>
        </div>
      </div>
    );
  }

  return (
    <div className="py-6">
      <div className="flex items-center justify-between relative">
        {/* Progress Line */}
        <div className="absolute left-0 right-0 top-1/2 h-1 bg-gray-200 -translate-y-1/2 z-0" />
        <div 
          className="absolute left-0 top-1/2 h-1 bg-primary-500 -translate-y-1/2 z-0 transition-all duration-500"
          style={{ width: `${(currentIndex / (STATUS_FLOW.length - 1)) * 100}%` }}
        />
        
        {/* Steps */}
        {STATUS_FLOW.map((step, index) => {
          const isCompleted = index <= currentIndex;
          const isCurrent = index === currentIndex;
          const Icon = step.icon;
          
          return (
            <div key={step.id} className="relative z-10 flex flex-col items-center">
              <div 
                className={`
                  w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300
                  ${isCompleted 
                    ? 'bg-primary-500 text-white shadow-lg shadow-primary-500/30' 
                    : 'bg-white border-2 border-gray-200 text-gray-400'}
                  ${isCurrent ? 'ring-4 ring-primary-100 scale-110' : ''}
                `}
              >
                {isCompleted && index < currentIndex ? (
                  <CheckIcon className="w-5 h-5" />
                ) : (
                  <Icon className="w-5 h-5" />
                )}
              </div>
              <span 
                className={`
                  mt-2 text-xs font-medium whitespace-nowrap
                  ${isCompleted ? 'text-primary-600' : 'text-gray-400'}
                `}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export const OrderDetailPageNew: React.FC = () => {
  const { id, storeId: routeStoreId } = useParams<{ id: string; storeId?: string }>();
  const navigate = useNavigate();
  const { printOrder } = useOrderPrint();
  const { store } = useStore();
  const storeRouteBase = routeStoreId || store?.slug || store?.id || null;
  const ordersRoute = storeRouteBase ? `/stores/${storeRouteBase}/orders` : '/stores';
  
  const [order, setOrder] = useState<Order | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showCancelModal, setShowCancelModal] = useState(false);

  useEffect(() => {
    if (id) loadOrder();
  }, [id]);

  const loadOrder = async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const [orderData, paymentsData] = await Promise.all([
        ordersService.getOrder(id),
        paymentsService.getByOrder(id).catch(() => []),
      ]);
      setOrder(orderData);
      setPayments(paymentsData);
    } catch (error) {
      toast.error(getErrorMessage(error));
      navigate(ordersRoute);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAction = async (action: string) => {
    if (!order) return;
    setActionLoading(action);
    try {
      let updated: Order;
      switch (action) {
        case 'confirm':
          updated = await ordersService.confirmOrder(order.id);
          break;
        case 'prepare':
          updated = await ordersService.startPreparing(order.id);
          break;
        case 'ready':
          updated = await ordersService.markReady(order.id);
          break;
        case 'deliver':
          updated = await ordersService.markOutForDelivery(order.id);
          break;
        case 'complete':
          updated = await ordersService.deliverOrder(order.id);
          break;
        case 'cancel':
          updated = await ordersService.cancelOrder(order.id);
          setShowCancelModal(false);
          break;
        default:
          return;
      }
      setOrder(updated);
      toast.success('Status atualizado!');
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setActionLoading(null);
    }
  };

  // Get next action based on current status
  const nextAction = useMemo(() => {
    if (!order) return null;
    const status = order.status.toLowerCase();
    
    const actions: Record<string, { action: string; label: string; color: string }> = {
      pending: { action: 'confirm', label: 'Confirmar Pedido', color: 'bg-blue-500 hover:bg-blue-600' },
      confirmed: { action: 'prepare', label: 'Iniciar Preparo', color: 'bg-orange-500 hover:bg-orange-600' },
      paid: { action: 'prepare', label: 'Iniciar Preparo', color: 'bg-orange-500 hover:bg-orange-600' },
      preparing: { action: 'ready', label: 'Marcar como Pronto', color: 'bg-purple-500 hover:bg-purple-600' },
      processing: { action: 'ready', label: 'Marcar como Pronto', color: 'bg-purple-500 hover:bg-purple-600' },
      ready: { action: 'deliver', label: 'Saiu para Entrega', color: 'bg-indigo-500 hover:bg-indigo-600' },
      out_for_delivery: { action: 'complete', label: 'Marcar Entregue', color: 'bg-green-500 hover:bg-green-600' },
      shipped: { action: 'complete', label: 'Marcar Entregue', color: 'bg-green-500 hover:bg-green-600' },
    };
    
    return actions[status] || null;
  }, [order]);

  const isCancelled = order?.status.toLowerCase() === 'cancelled';
  const isCompleted = ['delivered', 'completed'].includes(order?.status.toLowerCase() || '');

  if (isLoading || !order) {
    return <PageLoading />;
  }

  const statusColors = STATUS_COLORS[order.status.toLowerCase()] || STATUS_COLORS.pending;
  const address = order.delivery_address || order.shipping_address;
  const paymentStatus = order.payment_status || 'pending';
  const paymentStatusLabel: Record<string, string> = {
    pending: 'Pendente',
    processing: 'Processando',
    paid: 'Pago',
    failed: 'Falhou',
    refunded: 'Reembolsado',
  };
  const paymentMethodLabel: Record<string, string> = {
    pix: 'PIX',
    credit_card: 'Cartão de Crédito',
    debit_card: 'Cartão de Débito',
    cash: 'Dinheiro',
    card: 'Cartão',
    mercadopago: 'Mercado Pago',
  };
  const paymentLink = order.pix_ticket_url || order.payment_url || order.payment_link || order.init_point || null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-black">
      {/* Header */}
      <div className="bg-white dark:bg-zinc-900 border-b sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate(ordersRoute)}
                className="p-2 hover:bg-gray-100 dark:hover:bg-zinc-700 dark:bg-gray-700 rounded-lg transition-colors"
              >
                <ArrowLeftIcon className="w-5 h-5 text-gray-600 dark:text-zinc-400" />
              </button>
              <div>
                <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                  Pedido #{order.order_number}
                </h1>
                <p className="text-sm text-gray-500 dark:text-zinc-400">
                  {format(new Date(order.created_at), "dd 'de' MMMM 'às' HH:mm", { locale: ptBR })}
                </p>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              <span className={`px-4 py-2 rounded-full text-sm font-semibold ${statusColors.bg} ${statusColors.text}`}>
                {STATUS_LABELS[order.status.toLowerCase()] || order.status}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Progress Timeline */}
        <Card className="p-6">
          <ProgressTimeline currentStatus={order.status} isCancelled={isCancelled} />
          
          {/* Action Button */}
          {nextAction && !isCancelled && !isCompleted && (
            <div className="flex justify-center pt-4 border-t">
              <button
                onClick={() => handleAction(nextAction.action)}
                disabled={!!actionLoading}
                className={`
                  px-8 py-3 rounded-xl text-white font-semibold text-lg
                  transition-all duration-200 transform hover:scale-105
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${nextAction.color}
                `}
              >
                {actionLoading === nextAction.action ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Processando...
                  </span>
                ) : (
                  nextAction.label
                )}
              </button>
            </div>
          )}
        </Card>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Order Items */}
          <div className="lg:col-span-2 space-y-6">
            {/* Items */}
            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Itens do Pedido</h2>
              <div className="space-y-3">
                {order.items?.map((item, index) => (
                  <div 
                    key={item.id || index}
                    className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0"
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center text-lg">
                        🍝
                      </div>
                      <div>
                        <p className="font-medium text-gray-900 dark:text-white">{item.product_name}</p>
                        <p className="text-sm text-gray-500 dark:text-zinc-400">
                          {item.quantity}x {formatMoney(item.unit_price)}
                        </p>
                      </div>
                    </div>
                    <p className="font-semibold text-gray-900 dark:text-white">
                      {formatMoney(item.subtotal || item.total_price)}
                    </p>
                  </div>
                ))}
              </div>

              {/* Summary */}
              <div className="mt-6 pt-4 border-t border-gray-200 dark:border-zinc-800 space-y-2">
                <div className="flex justify-between text-gray-600 dark:text-zinc-400">
                  <span>Subtotal</span>
                  <span>{formatMoney(order.subtotal)}</span>
                </div>
                {(order.delivery_fee || order.shipping_cost) ? (
                  <div className="flex justify-between text-gray-600 dark:text-zinc-400">
                    <span>Entrega</span>
                    <span>{formatMoney(order.delivery_fee || order.shipping_cost)}</span>
                  </div>
                ) : null}
                {order.discount ? (
                  <div className="flex justify-between text-green-600 dark:text-green-400">
                    <span>Desconto</span>
                    <span>-{formatMoney(order.discount)}</span>
                  </div>
                ) : null}
                <div className="flex justify-between text-xl font-bold text-gray-900 dark:text-white pt-2">
                  <span>Total</span>
                  <span>{formatMoney(order.total)}</span>
                </div>
              </div>
            </Card>

            {/* Notes */}
            {order.notes && (
              <Card className="p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Observações</h2>
                <p className="text-gray-600 dark:text-zinc-400 bg-yellow-50 p-4 rounded-lg border border-yellow-100">
                  {order.notes}
                </p>
              </Card>
            )}
          </div>

          {/* Right Column - Customer & Delivery */}
          <div className="space-y-6">
            {/* Customer */}
            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Cliente</h2>
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-primary-100 rounded-full flex items-center justify-center">
                    <span className="text-lg font-semibold text-primary-600">
                      {(order.customer_name || 'C')[0].toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <p className="font-semibold text-gray-900 dark:text-white">{order.customer_name || 'Cliente'}</p>
                  </div>
                </div>
                
                {order.customer_phone && (
                  <a 
                    href={`tel:${order.customer_phone}`}
                    className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-black rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-800 transition-colors"
                  >
                    <PhoneIcon className="w-5 h-5 text-gray-400" />
                    <span className="text-gray-700 dark:text-zinc-300">{order.customer_phone}</span>
                  </a>
                )}
                
                {order.customer_email && (
                  <a 
                    href={`mailto:${order.customer_email}`}
                    className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-black rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-800 transition-colors"
                  >
                    <EnvelopeIcon className="w-5 h-5 text-gray-400" />
                    <span className="text-gray-700 dark:text-zinc-300 text-sm truncate">{order.customer_email}</span>
                  </a>
                )}
              </div>
            </Card>

            {/* Delivery Address */}
            {address && Object.keys(address).length > 0 && (
              <Card className="p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Entrega</h2>
                <div className="flex items-start gap-3">
                  <MapPinIcon className="w-5 h-5 text-gray-400 mt-0.5" />
                  <div className="text-gray-700 dark:text-zinc-300">
                    <p className="font-medium">
                      {(address as Record<string, string>).street || (address as Record<string, string>).address}
                      {(address as Record<string, string>).number && `, ${(address as Record<string, string>).number}`}
                    </p>
                    {(address as Record<string, string>).complement && (
                      <p className="text-sm text-gray-500 dark:text-zinc-400">{(address as Record<string, string>).complement}</p>
                    )}
                    <p className="text-sm">
                      {(address as Record<string, string>).neighborhood && `${(address as Record<string, string>).neighborhood}, `}
                      {(address as Record<string, string>).city} - {(address as Record<string, string>).state}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-zinc-400">
                      CEP: {(address as Record<string, string>).zip_code || (address as Record<string, string>).cep}
                    </p>
                  </div>
                </div>
              </Card>
            )}

            {/* Payment */}
            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Pagamento</h2>
              {payments.length > 0 ? (
                <div className="space-y-3">
                  {payments.map((payment) => (
                    <div key={payment.id} className="p-3 bg-gray-50 dark:bg-black rounded-lg">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-gray-900 dark:text-white">
                          {payment.payment_method === 'pix' ? '💠 PIX' : 
                           payment.payment_method === 'credit_card' ? '💳 Cartão' :
                           payment.payment_method === 'cash' ? '💵 Dinheiro' :
                           payment.payment_method}
                        </span>
                        <span className={`text-sm font-medium ${
                          ['paid', 'approved', 'completed'].includes(payment.status) 
                            ? 'text-green-600' 
                            : 'text-yellow-600'
                        }`}>
                          {['paid', 'approved', 'completed'].includes(payment.status) ? '✓ Pago' : '⏳ Pendente'}
                        </span>
                      </div>
                      <p className="text-lg font-bold text-gray-900 dark:text-white mt-1">
                        {formatMoney(payment.amount)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500 dark:text-zinc-400">Método</span>
                    <span className="font-medium text-gray-900 dark:text-white">
                      {paymentMethodLabel[order.payment_method || ''] || order.payment_method || '-'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500 dark:text-zinc-400">Status</span>
                    <span className={`text-sm font-semibold ${paymentStatus === 'paid' ? 'text-green-600' : paymentStatus === 'failed' ? 'text-red-600' : 'text-yellow-600'}`}>
                      {paymentStatusLabel[paymentStatus] || paymentStatus}
                    </span>
                  </div>
                  {order.pix_code && (
                    <div className="text-xs text-gray-500 dark:text-zinc-400 break-all bg-gray-50 dark:bg-black rounded-lg p-3">
                      <span className="font-semibold text-gray-700 dark:text-zinc-300">PIX:</span> {order.pix_code}
                    </div>
                  )}
                  {paymentLink && (
                    <a
                      href={paymentLink}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center justify-center w-full px-4 py-2 rounded-lg bg-primary-50 text-primary-700 hover:bg-primary-100 transition-colors"
                    >
                      Abrir link de pagamento
                    </a>
                  )}
                </div>
              )}
            </Card>

            {/* Actions */}
            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Ações</h2>
              <div className="space-y-2">
                <button
                  onClick={() => printOrder(order as any, {
                    storeName: store?.name || order.store_name || 'Loja',
                    storePhone: store?.phone || store?.whatsapp_number || '',
                    storeAddress: store?.address && store?.city && store?.state
                      ? `${store.address} - ${store.city}/${store.state}`
                      : (store?.address || store?.city || store?.state || ''),
                  })}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-primary-50 hover:bg-primary-100 rounded-lg transition-colors text-primary-700 font-medium"
                >
                  <PrinterIcon className="w-5 h-5" />
                  🖨️ Imprimir Pedido
                </button>
                {!isCancelled && !isCompleted && (
                  <button
                    onClick={() => setShowCancelModal(true)}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-50 hover:bg-red-100 dark:bg-red-900/40 rounded-lg transition-colors text-red-600 dark:text-red-400"
                  >
                    <XMarkIcon className="w-5 h-5" />
                    Cancelar Pedido
                  </button>
                )}
              </div>
            </Card>
          </div>
        </div>
      </div>

      {/* Cancel Modal */}
      <Modal
        isOpen={showCancelModal}
        onClose={() => setShowCancelModal(false)}
        title="Cancelar Pedido"
      >
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-zinc-400">
            Tem certeza que deseja cancelar o pedido <strong>#{order.order_number}</strong>?
          </p>
          <p className="text-sm text-red-600 dark:text-red-400">
            Esta ação não pode ser desfeita.
          </p>
          <div className="flex justify-end gap-3 pt-4">
            <Button variant="secondary" onClick={() => setShowCancelModal(false)}>
              Voltar
            </Button>
            <Button 
              variant="danger" 
              onClick={() => handleAction('cancel')}
              isLoading={actionLoading === 'cancel'}
            >
              Confirmar Cancelamento
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default OrderDetailPageNew;
