/**
 * Orders Kanban Board
 * 
 * Drag-and-drop Kanban board for managing orders.
 * Features optimistic updates for smooth UX.
 * 
 * IMPORTANT: This component maintains its own internal state for orders
 * to enable smooth drag-and-drop with optimistic updates. External order
 * changes are merged carefully to avoid overwriting local updates.
 */
import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCorners,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragStartEvent,
  DragEndEvent,
  useDroppable,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import {
  ClockIcon,
  CheckCircleIcon,
  FireIcon,
  TruckIcon,
  HomeIcon,
  XCircleIcon,
  UserIcon,
  PhoneIcon,
  CurrencyDollarIcon,
  MapPinIcon,
  ArrowPathIcon,
  CheckIcon,
} from '@heroicons/react/24/outline';
import { Order } from '../../types';

// Order status configuration - SEMANTIC FLOW
// Separates "order received" from "payment confirmed" for clarity
export const ORDER_STATUSES = [
  { 
    id: 'pending', 
    label: 'Recebido', 
    color: 'bg-gray-50 border-gray-300',
    headerColor: 'bg-gray-500',
    icon: ClockIcon,
    aliases: ['pendente', 'received'],
    description: 'Pedido recebido, aguardando ação'
  },
  { 
    id: 'processing', 
    label: 'Processando', 
    color: 'bg-amber-50 border-amber-300',
    headerColor: 'bg-amber-500',
    icon: CurrencyDollarIcon,
    aliases: ['awaiting_payment', 'payment_pending'],
    description: 'Pagamento em processamento'
  },
  { 
    id: 'confirmed', 
    label: 'Confirmado', 
    color: 'bg-blue-50 border-blue-200',
    headerColor: 'bg-blue-500',
    icon: CheckCircleIcon,
    aliases: ['confirmado', 'aprovado', 'paid', 'payment_confirmed'],
    description: 'Pagamento confirmado - Pronto para produção'
  },
  { 
    id: 'preparing', 
    label: 'Preparando', 
    color: 'bg-orange-50 border-orange-200',
    headerColor: 'bg-orange-500',
    icon: FireIcon,
    aliases: ['preparando', 'in_production'],
    description: 'Em produção na cozinha'
  },
  { 
    id: 'ready', 
    label: 'Pronto', 
    color: 'bg-purple-50 border-purple-200',
    headerColor: 'bg-purple-500',
    icon: CheckCircleIcon,
    aliases: ['pronto', 'ready_for_pickup', 'ready_for_delivery'],
    description: 'Pronto para entrega/retirada'
  },
  { 
    id: 'out_for_delivery', 
    label: 'Em Entrega', 
    color: 'bg-indigo-50 border-indigo-200',
    headerColor: 'bg-indigo-500',
    icon: TruckIcon,
    aliases: ['shipped', 'enviado', 'em_entrega', 'delivering'],
    description: 'Saiu para entrega'
  },
  { 
    id: 'delivered', 
    label: 'Entregue', 
    color: 'bg-green-50 border-green-200',
    headerColor: 'bg-green-500',
    icon: HomeIcon,
    aliases: ['entregue', 'completed'],
    description: 'Pedido finalizado'
  },
  { 
    id: 'cancelled', 
    label: 'Cancelado', 
    color: 'bg-red-50 border-red-200',
    headerColor: 'bg-red-500',
    icon: XCircleIcon,
    aliases: ['cancelado', 'refunded', 'failed'],
    description: 'Pedido cancelado'
  },
];

type OrderStatus = Order['status'];

// Helper to normalize status
const normalizeStatus = (status: string): OrderStatus => {
  const normalized = status.toLowerCase();
  for (const s of ORDER_STATUSES) {
    if (s.id === normalized || s.aliases.includes(normalized)) {
      return s.id as OrderStatus;
    }
  }
  return 'pending';
};

// Get status config
const getStatusConfig = (status: string) => {
  const normalized = normalizeStatus(status);
  return ORDER_STATUSES.find(s => s.id === normalized) || ORDER_STATUSES[0];
};

const formatCurrency = (value: number | string | null | undefined) => {
  const num = typeof value === 'string' ? Number(value) : value ?? 0;
  return num.toLocaleString('pt-BR', { minimumFractionDigits: 2 });
};

const getItemsCount = (order: Order) => order.items_count ?? order.items?.length ?? 0;

const formatAddress = (address: Order['delivery_address']) => {
  if (!address) return null;
  if (typeof address === 'string') return address;
  const addr = address as Record<string, string>;
  const parts = [
    addr.street || addr.rua || addr.logradouro,
    addr.number || addr.numero,
    addr.complement || addr.complemento,
    addr.neighborhood || addr.bairro,
    addr.city || addr.cidade,
    addr.state || addr.estado,
  ].filter(Boolean);
  return parts.join(', ');
};

interface OrderCardProps {
  order: Order;
  onClick?: (order: Order) => void;
  isDragging?: boolean;
  isUpdating?: boolean;
  isSuccess?: boolean;
}

// Sortable Order Card
const SortableOrderCard: React.FC<OrderCardProps> = ({ order, onClick, isUpdating, isSuccess }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: order.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <OrderCard order={order} onClick={onClick} isDragging={isDragging} isUpdating={isUpdating} isSuccess={isSuccess} />
    </div>
  );
};

// Payment Status Badge Component
const PaymentBadge: React.FC<{ paymentStatus?: string; paymentMethod?: string }> = ({ 
  paymentStatus, 
  paymentMethod 
}) => {
  const configs: Record<string, { label: string; color: string; icon: string }> = {
    pending: { label: 'Aguardando', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300', icon: '💳' },
    processing: { label: 'Processando', color: 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300', icon: '⏳' },
    paid: { label: 'Pago', color: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300', icon: '✅' },
    failed: { label: 'Falhou', color: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300', icon: '❌' },
    refunded: { label: 'Reembolsado', color: 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300', icon: '↩️' },
    partially_refunded: { label: 'Reembolso Parcial', color: 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300', icon: '↩️' },
  };
  
  const status = paymentStatus?.toLowerCase() || 'pending';
  const config = configs[status] || configs.pending;
  
  // Show payment method for cash
  const isCash = paymentMethod?.toLowerCase() === 'cash' || paymentMethod?.toLowerCase() === 'dinheiro';
  
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${config.color}`}>
      <span>{config.icon}</span>
      <span>{isCash && status === 'pending' ? 'Dinheiro' : config.label}</span>
    </span>
  );
};

// Order Card Component
const OrderCard: React.FC<OrderCardProps> = ({ order, onClick, isDragging, isUpdating, isSuccess }) => {
  const derivedPaymentStatus = order.payment_status
    || (['paid', 'confirmed'].includes(order.status?.toLowerCase?.() || '')
      ? 'paid'
      : undefined);

  return (
    <div
      className={`
        bg-white dark:bg-zinc-900 rounded-lg shadow-sm border-2 p-3 mb-2 cursor-pointer
        transition-all duration-300 hover:shadow-md hover:border-primary-300 dark:hover:border-primary-500
        ${isDragging ? 'shadow-lg ring-2 ring-primary-500 scale-105' : ''}
        ${isUpdating ? 'opacity-70 border-primary-300' : ''}
        ${isSuccess ? 'border-green-400 bg-green-50 dark:bg-green-900/30 animate-pulse' : 'border-gray-100 dark:border-zinc-800'}
      `}
      onClick={() => !isUpdating && onClick?.(order)}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="font-bold text-gray-900 dark:text-white text-sm">
          #{order.order_number}
        </span>
        <div className="flex items-center gap-2">
          {isUpdating && (
            <ArrowPathIcon className="w-4 h-4 text-primary-500 animate-spin" />
          )}
          {isSuccess && (
            <div className="flex items-center gap-1 text-green-600 dark:text-green-400">
              <CheckIcon className="w-4 h-4" />
              <span className="text-xs font-medium">Movido!</span>
            </div>
          )}
          {!isUpdating && !isSuccess && (
            <span className="text-xs text-gray-500 dark:text-zinc-400">
              {format(new Date(order.created_at), 'HH:mm', { locale: ptBR })}
            </span>
          )}
        </div>
      </div>

      {/* Payment Status Badge - NEW */}
      <div className="mb-2">
        <PaymentBadge 
          paymentStatus={derivedPaymentStatus} 
          paymentMethod={order.payment_method} 
        />
      </div>

      {/* Customer */}
      <div className="flex items-center gap-1.5 mb-2">
        <UserIcon className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500" />
        <span className="text-sm text-gray-700 dark:text-zinc-300 truncate">
          {order.customer_name || 'Cliente'}
        </span>
      </div>

      {/* Phone */}
      {order.customer_phone && (
        <div className="flex items-center gap-1.5 mb-2">
          <PhoneIcon className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500" />
          <span className="text-xs text-gray-500 dark:text-zinc-400">{order.customer_phone}</span>
        </div>
      )}

      {/* Delivery Address */}
      {order.delivery_address && (
        <div className="flex items-start gap-1.5 mb-2">
          <MapPinIcon className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 mt-0.5" />
          <span className="text-xs text-gray-500 dark:text-zinc-400 line-clamp-2">
            {formatAddress(order.delivery_address) || 'Endereço não informado'}
          </span>
        </div>
      )}

      {/* Items count */}
      <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-100 dark:border-zinc-800">
        <span className="text-xs text-gray-500 dark:text-zinc-400">
          {getItemsCount(order)} item(ns)
        </span>
        <div className="flex items-center gap-1">
          <CurrencyDollarIcon className="w-4 h-4 text-green-600 dark:text-green-400" />
          <span className="font-bold text-green-600 dark:text-green-400">
            R$ {formatCurrency(order.total)}
          </span>
        </div>
      </div>

      {/* Store badge */}
      {order.store_name && (
        <div className="mt-2">
          <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-300 rounded-full">
            {order.store_name}
          </span>
        </div>
      )}
    </div>
  );
};

// Kanban Column
interface KanbanColumnProps {
  status: typeof ORDER_STATUSES[0];
  orders: Order[];
  onOrderClick?: (order: Order) => void;
  updatingOrders?: Set<string>;
  successOrders?: Set<string>;
  isOver?: boolean;
}

const KanbanColumn: React.FC<KanbanColumnProps> = ({ status, orders, onOrderClick, updatingOrders, successOrders }) => {
  const Icon = status.icon;
  
  // Make the column a drop target
  const { setNodeRef, isOver } = useDroppable({
    id: status.id,
  });
  
  return (
    <div 
      ref={setNodeRef}
      className={`
        flex flex-col min-w-[280px] max-w-[320px] rounded-xl border-2 transition-all duration-300
        ${status.color} dark:bg-zinc-900/50 dark:border-zinc-800
        ${isOver ? 'ring-2 ring-primary-500 ring-offset-2 dark:ring-offset-gray-900 scale-[1.02] border-primary-400 shadow-lg' : ''}
      `}
    >
      {/* Column Header */}
      <div className={`${status.headerColor} text-white px-4 py-3 rounded-t-xl`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="w-5 h-5" />
            <span className="font-semibold">{status.label}</span>
          </div>
          <span className="bg-white/20 px-2.5 py-1 rounded-full text-xs font-bold min-w-[28px] text-center">
            {orders.length}
          </span>
        </div>
      </div>

      {/* Column Content */}
      <div className={`
        flex-1 p-3 overflow-y-auto max-h-[calc(100vh-280px)] min-h-[200px]
        transition-all duration-300
        ${isOver ? 'bg-primary-50/50 dark:bg-primary-900/20' : ''}
      `}>
        <SortableContext items={orders.map(o => o.id)} strategy={verticalListSortingStrategy}>
          {orders.length === 0 ? (
            <div className={`
              text-center py-8 text-sm border-2 border-dashed rounded-xl
              transition-all duration-300
              ${isOver ? 'border-primary-400 text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/30 scale-105' : 'border-gray-200 dark:border-zinc-700 text-gray-400 dark:text-gray-500'}
            `}>
              {isOver ? (
                <div className="flex flex-col items-center gap-2">
                  <CheckIcon className="w-6 h-6" />
                  <span>Solte aqui</span>
                </div>
              ) : 'Nenhum pedido'}
            </div>
          ) : (
            orders.map((order) => (
              <SortableOrderCard
                key={order.id}
                order={order}
                onClick={onOrderClick}
                isUpdating={updatingOrders?.has(order.id)}
                isSuccess={successOrders?.has(order.id)}
              />
            ))
          )}
        </SortableContext>
      </div>
    </div>
  );
};

// Main Kanban Component
interface OrdersKanbanProps {
  orders: Order[];
  onOrderClick?: (order: Order) => void;
  onStatusChange?: (orderId: string, newStatus: OrderStatus) => Promise<void>;
  visibleStatuses?: string[];
}

// Local status overrides - completely managed by Kanban
interface LocalOrderState {
  status: OrderStatus;
  originalStatus: OrderStatus;
  timestamp: number;
  isPending: boolean; // API call in progress
  isConfirmed: boolean; // API returned success
}

// How long to keep local state after confirmation (in ms)
const LOCAL_STATE_TTL = 60000; // 60 seconds - external data should sync by then

export const OrdersKanban: React.FC<OrdersKanbanProps> = ({
  orders: externalOrders,
  onOrderClick,
  onStatusChange,
  visibleStatuses,
}) => {
  const [activeId, setActiveId] = useState<string | null>(null);
  
  // LOCAL STATE: This is the source of truth for order statuses in Kanban
  // It persists until external data matches OR TTL expires
  const [localOrderStates, setLocalOrderStates] = useState<Map<string, LocalOrderState>>(new Map());
  
  // Success animation state
  const [successOrders, setSuccessOrders] = useState<Set<string>>(new Set());

  // Cleanup: Only remove local state when external data matches
  useEffect(() => {
    const now = Date.now();
    
    setLocalOrderStates(prev => {
      const next = new Map(prev);
      let hasChanges = false;
      
      for (const [orderId, state] of prev.entries()) {
        if (!state.isConfirmed) continue; // Keep pending states
        
        const externalOrder = externalOrders.find(o => o.id === orderId);
        
        if (!externalOrder) {
          // Order no longer exists - remove local state
          next.delete(orderId);
          hasChanges = true;
          continue;
        }
        
        // ONLY remove local state if external matches our confirmed status
        if (externalOrder.status === state.status) {
          // External caught up! Safe to remove local state
          next.delete(orderId);
          hasChanges = true;
          console.log(`[Kanban] External synced for ${orderId}: ${state.status}`);
        } else if (now - state.timestamp > LOCAL_STATE_TTL) {
          // TTL expired but external doesn't match - keep local state anyway
          // This prevents the "snap back" issue
          console.log(`[Kanban] TTL expired but keeping local state for ${orderId} (external: ${externalOrder.status}, local: ${state.status})`);
        }
      }
      
      return hasChanges ? next : prev;
    });
  }, [externalOrders]);

  // Compute effective orders - local state ALWAYS takes precedence for confirmed orders
  const effectiveOrders = useMemo(() => {
    return externalOrders.map(order => {
      const localState = localOrderStates.get(order.id);
      
      if (localState && (localState.isPending || localState.isConfirmed)) {
        // ALWAYS use local status if we have it
        // This prevents WebSocket/refresh from overwriting our confirmed changes
        return { ...order, status: localState.status };
      }
      
      return order;
    });
  }, [externalOrders, localOrderStates]);
  
  // Get updating orders for UI
  const updatingOrders = useMemo(() => {
    const updating = new Set<string>();
    localOrderStates.forEach((state, id) => {
      if (state.isPending) {
        updating.add(id);
      }
    });
    return updating;
  }, [localOrderStates]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Group orders by status - using effectiveOrders which includes local overrides
  const ordersByStatus = useMemo(() => {
    const grouped: Record<string, Order[]> = {};
    
    ORDER_STATUSES.forEach(status => {
      grouped[status.id] = [];
    });

    effectiveOrders.forEach(order => {
      const normalizedStatus = normalizeStatus(order.status);
      if (grouped[normalizedStatus]) {
        grouped[normalizedStatus].push(order);
      } else {
        grouped['pending'].push(order);
      }
    });

    // Sort by created_at within each column
    Object.keys(grouped).forEach(status => {
      grouped[status].sort((a, b) => 
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    });

    return grouped;
  }, [effectiveOrders]);

  // Filter visible statuses
  const displayStatuses = useMemo(() => {
    if (!visibleStatuses || visibleStatuses.length === 0) {
      return ORDER_STATUSES.filter(s => !['cancelled', 'delivered'].includes(s.id));
    }
    return ORDER_STATUSES.filter(s => visibleStatuses.includes(s.id));
  }, [visibleStatuses]);

  // Get active order for drag overlay
  const activeOrder = useMemo(() => {
    if (!activeId) return null;
    return effectiveOrders.find(o => o.id === activeId) || null;
  }, [activeId, effectiveOrders]);

  // Find which column an order is in
  const findColumn = useCallback((orderId: string): string | null => {
    for (const [status, statusOrders] of Object.entries(ordersByStatus)) {
      if (statusOrders.some(o => o.id === orderId)) {
        return status;
      }
    }
    return null;
  }, [ordersByStatus]);

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);

    if (!over) return;

    const activeOrderId = active.id as string;
    const overId = over.id as string;

    // Find source column
    const sourceColumn = findColumn(activeOrderId);
    
    // Determine destination column
    // First check if dropped directly on a column (status id)
    let destColumn: string | null = null;
    
    // Check if overId is a status column
    const isStatusColumn = ORDER_STATUSES.some(s => s.id === overId);
    if (isStatusColumn) {
      destColumn = overId;
    } else {
      // Dropped on another order card - find which column that card is in
      destColumn = findColumn(overId);
    }

    // Validate
    if (!sourceColumn || !destColumn) {
      console.log('Invalid drag: source or dest column not found');
      return;
    }
    
    if (sourceColumn === destColumn) {
      console.log('Same column, no change needed');
      return;
    }

    console.log(`[Kanban] Moving order ${activeOrderId} from ${sourceColumn} to ${destColumn}`);

    // Get current order to preserve original status for potential rollback
    const currentOrder = effectiveOrders.find(o => o.id === activeOrderId);
    const originalStatus = currentOrder?.status || normalizeStatus(sourceColumn || 'pending');
    const nextStatus = normalizeStatus(destColumn);

    // OPTIMISTIC UPDATE: Set local state immediately
    setLocalOrderStates(prev => {
      const next = new Map(prev);
      next.set(activeOrderId, {
        status: nextStatus,
        originalStatus: originalStatus,
        timestamp: Date.now(),
        isPending: true,
        isConfirmed: false,
      });
      return next;
    });

    // Call API in background
    if (onStatusChange) {
      try {
        await onStatusChange(activeOrderId, nextStatus);
        console.log(`[Kanban] ✅ Successfully updated order ${activeOrderId} to ${nextStatus}`);
        
        // Mark as confirmed - keep local state active
        setLocalOrderStates(prev => {
          const next = new Map(prev);
          const current = next.get(activeOrderId);
          if (current) {
            next.set(activeOrderId, {
              ...current,
              isPending: false,
              isConfirmed: true,
              timestamp: Date.now(), // Reset timer
            });
          }
          return next;
        });
        
        // Show success animation
        setSuccessOrders(prev => new Set(prev).add(activeOrderId));
        setTimeout(() => {
          setSuccessOrders(prev => {
            const next = new Set(prev);
            next.delete(activeOrderId);
            return next;
          });
        }, 2000);
        
        // NOTE: Don't clear local state with setTimeout!
        // The cleanup useEffect will remove it when external data matches
        
      } catch (error) {
        // ROLLBACK: Revert to original status on error
        console.error('[Kanban] ❌ Failed to update order status:', error);
        setLocalOrderStates(prev => {
          const next = new Map(prev);
          next.delete(activeOrderId); // Remove override, will use external status
          return next;
        });
      }
    } else {
      // No onStatusChange handler - just mark as confirmed
      setLocalOrderStates(prev => {
        const next = new Map(prev);
        const current = next.get(activeOrderId);
        if (current) {
          next.set(activeOrderId, {
            ...current,
            isPending: false,
            isConfirmed: true,
          });
        }
        return next;
      });
    }
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto pb-4 px-1">
        {displayStatuses.map((status) => (
          <KanbanColumn
            key={status.id}
            status={status}
            orders={ordersByStatus[status.id] || []}
            onOrderClick={onOrderClick}
            updatingOrders={updatingOrders}
            successOrders={successOrders}
          />
        ))}
      </div>

      {/* Drag Overlay - Enhanced with shadow and rotation */}
      <DragOverlay>
        {activeOrder ? (
          <div className="rotate-2 scale-105 shadow-2xl">
            <OrderCard order={activeOrder} isDragging />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
};

export default OrdersKanban;
