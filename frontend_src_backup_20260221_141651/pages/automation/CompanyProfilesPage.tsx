import React, { useState, useEffect } from 'react';
import logger from '../../services/logger';
import { Link } from 'react-router-dom';
import {
  PlusIcon,
  BuildingOfficeIcon,
  Cog6ToothIcon,
  ChartBarIcon,
  KeyIcon,
} from '@heroicons/react/24/outline';
import { companyProfileApi, businessTypeLabels } from '../../services/automation';
import { CompanyProfile } from '../../types';
import { Loading as LoadingSpinner } from '../../components/common/Loading';
import { toast } from 'react-hot-toast';

const CompanyProfilesPage: React.FC = () => {
  const [profiles, setProfiles] = useState<CompanyProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    loadProfiles();
  }, [page]);

  const loadProfiles = async () => {
    try {
      setLoading(true);
      const response = await companyProfileApi.list({ page, page_size: 20 });
      setProfiles(response.results);
      setTotalCount(response.count);
    } catch (error) {
      toast.error('Erro ao carregar perfis de empresa');
      logger.error('Failed to load company profiles', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerateApiKey = async (id: string) => {
    if (!confirm('Tem certeza que deseja gerar uma nova API key? A chave atual será invalidada.')) {
      return;
    }
    try {
      const result = await companyProfileApi.regenerateApiKey(id);
      toast.success('Nova API key gerada!');
      navigator.clipboard.writeText(result.api_key);
      toast.success('API key copiada para a área de transferência');
      loadProfiles();
    } catch (error) {
      toast.error('Erro ao gerar nova API key');
    }
  };

  if (loading && profiles.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Perfis de Empresa</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-zinc-400">
            Configure automações para cada número WhatsApp
          </p>
        </div>
        <Link
          to="/automation/companies/new"
          className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700"
        >
          <PlusIcon className="h-5 w-5 mr-2" />
          Novo Perfil
        </Link>
      </div>

      {/* Profiles Grid */}
      {profiles.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-zinc-900 rounded-lg shadow">
          <BuildingOfficeIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-white">Nenhum perfil configurado</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-zinc-400">
            Crie um perfil de empresa para começar a usar automações.
          </p>
          <div className="mt-6">
            <Link
              to="/automation/companies/new"
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700"
            >
              <PlusIcon className="h-5 w-5 mr-2" />
              Criar Perfil
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {profiles.map((profile) => (
            <div
              key={profile.id}
              className="bg-white dark:bg-zinc-900 rounded-lg shadow hover:shadow-md transition-shadow"
            >
              <div className="p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <div className="flex-shrink-0">
                      <BuildingOfficeIcon className="h-10 w-10 text-green-600 dark:text-green-400" />
                    </div>
                    <div className="ml-4">
                      <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                        {profile.company_name}
                      </h3>
                      <p className="text-sm text-gray-500 dark:text-zinc-400">
                        {profile.account_phone}
                      </p>
                    </div>
                  </div>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    profile.auto_reply_enabled
                      ? 'bg-green-100 text-green-800'
                      : 'bg-gray-100 text-gray-800'
                  }`}>
                    {profile.auto_reply_enabled ? 'Ativo' : 'Inativo'}
                  </span>
                </div>

                <div className="mt-4 space-y-2">
                  <div className="flex items-center text-sm text-gray-500 dark:text-zinc-400">
                    <span className="font-medium mr-2">Tipo:</span>
                    {businessTypeLabels[profile.business_type] || profile.business_type}
                  </div>
                  {profile.website_url && (
                    <div className="flex items-center text-sm text-gray-500 dark:text-zinc-400 truncate">
                      <span className="font-medium mr-2">Site:</span>
                      <a
                        href={profile.website_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-green-600 dark:text-green-400 hover:text-green-700 dark:text-green-300 truncate"
                      >
                        {profile.website_url}
                      </a>
                    </div>
                  )}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {profile.welcome_message_enabled && (
                    <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-800">
                      Boas-vindas
                    </span>
                  )}
                  {profile.abandoned_cart_notification && (
                    <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800">
                      Carrinho abandonado
                    </span>
                  )}
                  {profile.pix_notification_enabled && (
                    <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-purple-100 dark:bg-purple-900/40 text-purple-800">
                      PIX
                    </span>
                  )}
                  {profile.use_ai_agent && (
                    <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-indigo-100 text-indigo-800">
                      Agente IA
                    </span>
                  )}
                </div>

                <div className="mt-6 flex items-center justify-between border-t pt-4">
                  <div className="flex space-x-2">
                    <Link
                      to={`/automation/companies/${profile.id}`}
                      className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-zinc-700 rounded-md text-sm font-medium text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black"
                    >
                      <Cog6ToothIcon className="h-4 w-4 mr-1" />
                      Configurar
                    </Link>
                    <Link
                      to={`/automation/companies/${profile.id}/stats`}
                      className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-zinc-700 rounded-md text-sm font-medium text-gray-700 dark:text-zinc-300 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black"
                    >
                      <ChartBarIcon className="h-4 w-4 mr-1" />
                      Stats
                    </Link>
                  </div>
                  <button
                    onClick={() => handleRegenerateApiKey(profile.id)}
                    className="inline-flex items-center px-3 py-1.5 text-sm text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-300 dark:hover:text-zinc-300"
                    title="Gerar nova API key"
                  >
                    <KeyIcon className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalCount > 20 && (
        <div className="flex items-center justify-between border-t border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-4 py-3 sm:px-6 rounded-lg shadow">
          <div className="flex flex-1 justify-between sm:hidden">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="relative inline-flex items-center rounded-md border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2 text-sm font-medium text-gray-700 dark:text-zinc-300 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black disabled:opacity-50"
            >
              Anterior
            </button>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page * 20 >= totalCount}
              className="relative ml-3 inline-flex items-center rounded-md border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2 text-sm font-medium text-gray-700 dark:text-zinc-300 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black disabled:opacity-50"
            >
              Próximo
            </button>
          </div>
          <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
            <div>
              <p className="text-sm text-gray-700 dark:text-zinc-300">
                Mostrando <span className="font-medium">{(page - 1) * 20 + 1}</span> a{' '}
                <span className="font-medium">{Math.min(page * 20, totalCount)}</span> de{' '}
                <span className="font-medium">{totalCount}</span> resultados
              </p>
            </div>
            <div className="flex space-x-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="relative inline-flex items-center rounded-md border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2 text-sm font-medium text-gray-700 dark:text-zinc-300 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black disabled:opacity-50"
              >
                Anterior
              </button>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={page * 20 >= totalCount}
                className="relative inline-flex items-center rounded-md border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-4 py-2 text-sm font-medium text-gray-700 dark:text-zinc-300 hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black disabled:opacity-50"
              >
                Próximo
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CompanyProfilesPage;
