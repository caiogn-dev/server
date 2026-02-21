import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  HomeIcon,
  DevicePhoneMobileIcon,
  ChatBubbleLeftRightIcon,
  InboxIcon,
  ShoppingCartIcon,
  CreditCardIcon,
  CpuChipIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  BoltIcon,
  BuildingOfficeIcon,
  UserGroupIcon,
  DocumentTextIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  DocumentChartBarIcon,
  TagIcon,
  Squares2X2Icon,
  XMarkIcon,
  BuildingStorefrontIcon,
  PresentationChartLineIcon,
  MegaphoneIcon,
  EnvelopeIcon,
  PlusCircleIcon,
  MagnifyingGlassIcon,
  ChatBubbleBottomCenterTextIcon,
  FolderIcon,
  SparklesIcon,
  ShareIcon,
  ArchiveBoxIcon,
  ReceiptPercentIcon,
  QueueListIcon,
  Bars3BottomLeftIcon,
  SwatchIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '../../stores/authStore';
import { useStore } from '../../hooks/useStore';
import { useTotalUnreadCount, useWsConnected } from '../../stores/chatStore';
import { cn } from '../../utils/cn';

interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  children?: NavItem[];
  badge?: string;
  section?: string;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

interface SidebarProps {
  onClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ onClose }) => {
  const { logout, user } = useAuthStore();
  const { store } = useStore();
  const location = useLocation();
  const [expandedItems, setExpandedItems] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const totalUnreadCount = useTotalUnreadCount();
  const wsConnected = useWsConnected();

  const storeKey = store?.slug || store?.id || null;
  const storeRoot = storeKey ? `/stores/${storeKey}` : '/stores';
  const storeHref = useMemo(() => {
    return (path: string) => (storeKey ? `${storeRoot}/${path}` : '/stores');
  }, [storeKey, storeRoot]);

  // Menu reorganizado - ATUALIZADO COM TODAS FUNCIONALIDADES DO BACKEND
  const navigationSections: NavSection[] = useMemo(() => [
    {
      title: 'Principal',
      items: [
        { name: 'Dashboard', href: '/', icon: HomeIcon },
        { name: 'Pedidos', href: storeHref('orders'), icon: ShoppingCartIcon },
        { name: 'Produtos', href: storeHref('products'), icon: Squares2X2Icon },
        { name: 'Cupons', href: storeHref('coupons'), icon: TagIcon },
      ]
    },
    {
      title: 'Comunicação',
      items: [
        { 
          name: 'Conversas', 
          href: '/conversations', 
          icon: ChatBubbleLeftRightIcon,
          badge: totalUnreadCount > 0 ? String(totalUnreadCount) : undefined,
        },
        { 
          name: 'WhatsApp', 
          href: '/whatsapp/chat', 
          icon: DevicePhoneMobileIcon,
          children: [
            { name: 'Chat', href: '/whatsapp/chat', icon: ChatBubbleLeftRightIcon },
            { name: 'Contas', href: '/accounts', icon: DevicePhoneMobileIcon },
            { name: 'Templates', href: '/marketing/whatsapp/templates', icon: DocumentTextIcon },
            { name: 'Analytics', href: '/analytics', icon: PresentationChartLineIcon },
            { name: 'Diagnóstico', href: '/whatsapp/diagnostics', icon: Cog6ToothIcon },
          ]
        },
        { 
          name: 'Instagram', 
          href: '/instagram/inbox', 
          icon: ChatBubbleLeftRightIcon,
          children: [
            { name: 'Mensagens', href: '/instagram/inbox', icon: InboxIcon },
            { name: 'Contas', href: '/instagram/accounts', icon: UserGroupIcon },
          ]
        },
        { 
          name: 'Messenger', 
          href: '/messenger/inbox', 
          icon: ChatBubbleBottomCenterTextIcon,
          children: [
            { name: 'Mensagens', href: '/messenger/inbox', icon: InboxIcon },
            { name: 'Contas', href: '/messenger/accounts', icon: UserGroupIcon },
          ]
        },
        { 
          name: 'Marketing', 
          href: '/marketing', 
          icon: MegaphoneIcon,
          children: [
            { name: 'Dashboard', href: '/marketing', icon: MegaphoneIcon },
            { name: 'Campanhas Email', href: '/marketing/email/campaigns', icon: EnvelopeIcon },
            { name: 'Campanhas WhatsApp', href: '/marketing/whatsapp', icon: DevicePhoneMobileIcon },
            { name: 'Templates', href: '/marketing/whatsapp/templates', icon: DocumentTextIcon },
            { name: 'Assinantes', href: '/marketing/subscribers', icon: UserGroupIcon },
            { name: 'Automações', href: '/marketing/automations', icon: BoltIcon },
          ]
        },
      ]
    },
    {
      title: 'Automação & IA',
      items: [
        { 
          name: 'Agentes IA', 
          href: '/agents', 
          icon: CpuChipIcon,
          badge: 'Novo',
          children: [
            { name: 'Lista de Agentes', href: '/agents', icon: CpuChipIcon },
            { name: 'Testar Orquestrador', href: '/agents/test/orchestrator', icon: SparklesIcon },
          ]
        },
        {
          name: 'Automação',
          href: '/automation/companies',
          icon: BoltIcon,
          children: [
            { name: 'Empresas', href: '/automation/companies', icon: BuildingOfficeIcon },
            { name: 'Sessões Clientes', href: '/automation/sessions', icon: UserGroupIcon },
            { name: 'Agendamentos', href: '/automation/scheduled', icon: ClockIcon },
            { name: 'Logs', href: '/automation/logs', icon: DocumentChartBarIcon },
            { name: 'Relatórios', href: '/automation/reports', icon: DocumentChartBarIcon },
          ]
        },
        {
          name: 'Intenções (Novo)',
          href: '/automation/intents',
          icon: SparklesIcon,
          badge: 'Novo',
          children: [
            { name: 'Estatísticas', href: '/automation/intents', icon: PresentationChartLineIcon },
            { name: 'Logs de Intenções', href: '/automation/intents/logs', icon: DocumentChartBarIcon },
          ]
        },
      ]
    },
    {
      title: 'Analytics & Dados',
      items: [
        { name: 'Analytics', href: storeHref('analytics'), icon: PresentationChartLineIcon },
        { name: 'Relatórios', href: '/reports', icon: DocumentChartBarIcon },
        { 
          name: 'Lojas', 
          href: '/stores', 
          icon: BuildingStorefrontIcon,
          children: [
            { name: 'Todas Lojas', href: '/stores', icon: BuildingStorefrontIcon },
            { name: 'Configurações', href: storeHref('settings'), icon: Cog6ToothIcon },
            { name: 'Pagamentos', href: storeHref('payments'), icon: CreditCardIcon },
          ]
        },
      ]
    },
  ], [storeHref, totalUnreadCount]);
  
  
  // Filter items by search
  const filteredSections = useMemo(() => {
    if (!searchQuery.trim()) return navigationSections;
    
    const query = searchQuery.toLowerCase();
    return navigationSections
      .map(section => ({
        ...section,
        items: section.items.filter(item => 
          item.name.toLowerCase().includes(query) ||
          item.children?.some(child => child.name.toLowerCase().includes(query))
        )
      }))
      .filter(section => section.items.length > 0);
  }, [navigationSections, searchQuery]);

  // Dynamic brand info based on selected store
  const brandInfo = useMemo(() => {
    // Default Pastita branding with local SVG logo
    const defaultBrand = {
      name: 'Pastita',
      logo: '/pastita-logo.svg',
      primaryColor: '#722F37',
      secondaryColor: '#8B3A42',
      initial: 'P',
    };

    if (!store) return defaultBrand;

    // Check if it's Agrião based on store name or slug
    const isAgriao = store.name?.toLowerCase().includes('agriao') || 
                     store.slug?.toLowerCase().includes('agriao');

    if (isAgriao) {
      return {
        name: store.name || 'Agrião',
        logo: store.logo_url || null,
        primaryColor: '#4A5D23',
        secondaryColor: '#6B8E23',
        initial: 'A',
      };
    }

    // For Pastita stores, use local SVG logo
    const isPastita = store.name?.toLowerCase().includes('pastita') || 
                      store.slug?.toLowerCase().includes('pastita');

    return {
      name: store.name || 'Pastita',
      logo: isPastita ? '/pastita-logo.svg' : (store.logo_url || null),
      primaryColor: store.primary_color || '#722F37',
      secondaryColor: store.secondary_color || '#8B3A42',
      initial: store.name?.[0]?.toUpperCase() || 'P',
    };
  }, [store]);

  // Apply theme based on store
  useEffect(() => {
    const isAgriao = store?.name?.toLowerCase().includes('agriao') || 
                     store?.slug?.toLowerCase().includes('agriao');
    
    if (isAgriao) {
      document.documentElement.setAttribute('data-theme', 'agriao');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  }, [store]);

  const handleLogout = () => {
    logout();
    window.location.href = '/login';
  };

  const handleNavClick = () => {
    if (onClose) onClose();
  };

  const toggleExpand = (name: string) => {
    setExpandedItems(prev =>
      prev.includes(name)
        ? prev.filter(item => item !== name)
        : [...prev, name]
    );
  };

  const isItemActive = (item: NavItem): boolean => {
    if (location.pathname === item.href) return true;
    if (item.children) {
      return item.children.some(child => location.pathname.startsWith(child.href));
    }
    return false;
  };

  const renderNavItem = (item: NavItem, depth = 0) => {
    const hasChildren = item.children && item.children.length > 0;
    const isExpanded = expandedItems.includes(item.name);
    const isActive = isItemActive(item);

    if (hasChildren) {
      return (
        <div key={item.name}>
          <button
            onClick={() => toggleExpand(item.name)}
            className={`w-full flex items-center justify-between px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
              isActive 
                ? 'bg-primary-50 dark:bg-zinc-900 text-primary-700 dark:text-primary-400' 
                : 'text-gray-700 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-800'
            }`}
          >
            <div className="flex items-center">
              <item.icon className="w-5 h-5 mr-3" />
              {item.name}
            </div>
            <div className="flex items-center gap-1">
              {item.badge && (
                <span className="text-xs bg-primary-100 dark:bg-zinc-800 text-primary-700 dark:text-primary-400 px-1.5 py-0.5 rounded">
                  {item.badge}
                </span>
              )}
              {isExpanded ? (
                <ChevronDownIcon className="w-4 h-4" />
              ) : (
                <ChevronRightIcon className="w-4 h-4" />
              )}
            </div>
          </button>
          {isExpanded && (
            <div className="ml-4 mt-1 space-y-1 border-l-2 border-gray-100 dark:border-zinc-800 pl-2">
              {item.children!.map(child => renderNavItem(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    return (
      <NavLink
        key={item.name}
        to={item.href}
        end={item.href === '/'}
        onClick={handleNavClick}
        className={({ isActive }) =>
          `flex items-center justify-between px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
            isActive
              ? 'bg-primary-50 dark:bg-zinc-900 text-primary-700 dark:text-primary-400'
              : 'text-gray-700 dark:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-800'
          }`
        }
      >
        <div className="flex items-center">
          <item.icon className="w-5 h-5 mr-3" />
          {item.name}
        </div>
        {item.badge && (
          <span className="text-xs bg-primary-100 dark:bg-zinc-800 text-primary-700 dark:text-primary-400 px-1.5 py-0.5 rounded">
            {item.badge}
          </span>
        )}
      </NavLink>
    );
  };

  return (
    <div className="flex flex-col h-full bg-white dark:bg-black border-r border-gray-200 dark:border-zinc-800 w-64 transition-colors">
      {/* Dynamic Logo based on selected store */}
      <div className="flex items-center justify-between h-16 px-6 border-b border-gray-200 dark:border-zinc-800">
        <div className="flex items-center gap-3">
          {brandInfo.logo ? (
            <img 
              src={brandInfo.logo} 
              alt={brandInfo.name}
              className="w-10 h-10 rounded-xl object-cover shadow-sm"
              onError={(e) => {
                e.currentTarget.style.display = 'none';
                e.currentTarget.nextElementSibling?.classList.remove('hidden');
              }}
            />
          ) : null}
          <div 
            className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-sm transition-all duration-300 ${brandInfo.logo ? 'hidden' : ''}`}
            style={{ 
              background: `linear-gradient(135deg, ${brandInfo.primaryColor} 0%, ${brandInfo.secondaryColor} 100%)` 
            }}
          >
            <span className="text-white font-bold text-lg">{brandInfo.initial}</span>
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-gray-900 dark:text-white text-lg leading-tight truncate max-w-[120px]">
              {brandInfo.name}
            </span>
            <span className="text-xs text-gray-500 dark:text-zinc-400">Dashboard</span>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300 hover:bg-gray-100 dark:hover:bg-zinc-800 rounded-lg lg:hidden transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Quick Search */}
      <div className="px-3 py-2">
        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-zinc-500" />
          <input
            type="text"
            placeholder="Buscar menu..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={cn(
              'w-full pl-9 pr-3 py-2 text-sm',
              'bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800',
              'rounded-lg placeholder-gray-400 dark:placeholder-zinc-500',
              'text-gray-900 dark:text-zinc-100',
              'focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500',
              'transition-all duration-200'
            )}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 overflow-y-auto smooth-scroll">
        {filteredSections.map((section, index) => (
          <div key={section.title} className={cn('animate-fade-up', index > 0 ? 'mt-5' : '')}>
            <h3 className="px-3 mb-2 text-[10px] font-semibold text-gray-400 dark:text-zinc-500 uppercase tracking-wider">
              {section.title}
            </h3>
            <div className="space-y-0.5">
              {section.items.map((item) => renderNavItem(item))}
            </div>
          </div>
        ))}
        {filteredSections.length === 0 && searchQuery && (
          <div className="px-3 py-8 text-center">
            <p className="text-sm text-gray-500 dark:text-zinc-400">
              Nenhum item encontrado
            </p>
          </div>
        )}
      </nav>

      {/* User section */}
      <div className="p-4 border-t border-gray-200 dark:border-zinc-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <div className="w-8 h-8 bg-primary-100 dark:bg-zinc-800 rounded-full flex items-center justify-center">
              <span className="text-sm font-medium text-primary-700 dark:text-primary-400">
                {user?.first_name?.[0] || user?.username?.[0] || 'U'}
              </span>
            </div>
            <div className="ml-3">
              <p className="text-sm font-medium text-gray-900 dark:text-white">
                {user?.first_name || user?.username || 'Usuário'}
              </p>
              <p className="text-xs text-gray-500 dark:text-zinc-400 truncate max-w-[120px]">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300 rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
            title="Sair"
          >
            <ArrowRightOnRectangleIcon className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};
