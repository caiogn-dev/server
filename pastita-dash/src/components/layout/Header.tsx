import React, { useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { MagnifyingGlassIcon, Bars3Icon } from '@heroicons/react/24/outline';
import { useAccountStore } from '../../stores/accountStore';
import { NotificationDropdown } from '../notifications';
import { StoreSelector } from './StoreSelector';
import { ThemeToggle } from '../theme';

const BREADCRUMB_LABELS: Record<string, string> = {
  analytics: 'Analytics',
  accounts: 'Contas',
  agents: 'Agentes IA',
  automation: 'Automação',
  campaigns: 'Campanhas',
  conversations: 'Conversas',
  dashboard: 'Dashboard',
  delivery: 'Entrega',
  instagram: 'Instagram',
  marketing: 'Marketing',
  messages: 'Mensagens',
  messenger: 'Messenger',
  payments: 'Pagamentos',
  products: 'Produtos',
  reports: 'Relatórios',
  settings: 'Configurações',
  stores: 'Lojas',
  orders: 'Pedidos',
  whatsapp: 'WhatsApp',
};

const IDENTIFIER_PATTERN = /^[0-9a-f]{4,}-[0-9a-f]{2,}-[0-9a-f]{2,}/i;

const titleCase = (value: string) =>
  value
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());

const formatBreadcrumbLabel = (segment: string): string => {
  if (!segment) return 'Dashboard';
  const normalized = segment.toLowerCase();
  if (BREADCRUMB_LABELS[normalized]) {
    return BREADCRUMB_LABELS[normalized];
  }
  if (/^\d+$/.test(segment) || IDENTIFIER_PATTERN.test(segment)) {
    return 'Detalhes';
  }
  return titleCase(segment);
};

const buildBreadcrumbs = (pathname: string) => {
  const segments = pathname.split('/').filter(Boolean);
  const crumbs = [{ label: 'Dashboard', path: '/' }];

  segments.forEach((segment, index) => {
    crumbs.push({
      label: formatBreadcrumbLabel(segment),
      path: `/${segments.slice(0, index + 1).join('/')}`,
    });
  });

  return crumbs;
};

interface HeaderProps {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  showSearch?: boolean;
  showStoreSelector?: boolean;
  onSearch?: (query: string) => void;
  onMenuClick?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  title = 'Painel',
  subtitle,
  actions,
  showSearch = true,
  showStoreSelector = true,
  onSearch,
  onMenuClick,
}) => {
  const { accounts, selectedAccount, setSelectedAccount } = useAccountStore();
  const [searchQuery, setSearchQuery] = useState('');
  const location = useLocation();

  const breadcrumbs = useMemo(() => buildBreadcrumbs(location.pathname), [location.pathname]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch?.(searchQuery);
  };

  return (
    <header className="border-b border-gray-200 dark:border-zinc-800 bg-white dark:bg-black px-4 md:px-6 py-4 transition-colors">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex w-full items-start gap-4 md:items-center">
          {onMenuClick && (
            <button
              onClick={onMenuClick}
              className="lg:hidden rounded-lg border border-gray-200 bg-white/70 p-2 text-gray-600 transition hover:border-gray-300 hover:text-gray-900 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-300 dark:hover:border-zinc-600 dark:hover:text-white"
            >
              <Bars3Icon className="h-6 w-6" />
            </button>
          )}

          <div className="flex flex-1 flex-col gap-1 min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">{title}</h1>
              {subtitle && (
                <p className="text-sm text-gray-500 dark:text-zinc-400">{subtitle}</p>
              )}
            </div>
            <nav aria-label="Breadcrumb" className="mt-1">
              <ol className="flex flex-wrap items-center gap-2 text-xs font-medium text-gray-500 dark:text-zinc-400">
                {breadcrumbs.map((crumb, index) => {
                  const isLast = index === breadcrumbs.length - 1;
                  return (
                    <li key={`${crumb.path}-${index}`} className="flex items-center gap-1">
                      {!isLast ? (
                        <Link
                          to={crumb.path}
                          className="hover:text-gray-900 dark:hover:text-white"
                        >
                          {crumb.label}
                        </Link>
                      ) : (
                        <span className="text-gray-900 dark:text-white">{crumb.label}</span>
                      )}
                      {index < breadcrumbs.length - 1 && <span aria-hidden="true">/</span>}
                    </li>
                  );
                })}
              </ol>
            </nav>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {showStoreSelector && <StoreSelector />}

          {accounts.length > 0 && (
            <select
              value={selectedAccount?.id || ''}
              onChange={(e) => {
                const account = accounts.find((a) => a.id === e.target.value);
                setSelectedAccount(account || null);
              }}
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-[#722F37] focus:ring-2 focus:ring-[#722F37] focus:ring-offset-0 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            >
              <option value="">Todas as contas</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          )}

          {showSearch && (
            <form
              onSubmit={handleSearch}
              className="relative hidden min-w-[220px] sm:block"
            >
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400 dark:text-zinc-500" />
              <input
                type="text"
                placeholder="Buscar..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-4 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-[#722F37] focus:ring-2 focus:ring-[#722F37]/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
              />
            </form>
          )}

          <ThemeToggle />

          <NotificationDropdown />

          {actions}
        </div>
      </div>
    </header>
  );
};
