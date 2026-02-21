// @ts-nocheck
/**
 * Instagram Accounts Page
 * 
 * Lista todas as contas do Instagram conectadas,
 * permite conectar novas contas e sincronizar dados.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PlusIcon,
  ArrowPathIcon,
  TrashIcon,
  EyeIcon,
  ChartBarIcon,
  CameraIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { Card, Button, Loading, Modal, Badge, StatCard } from '@/components/common';
import { instagramAccountApi, InstagramAccount } from '@/services';
import { useFetch } from '@/hooks';

export const InstagramAccountsPage: React.FC = () => {
  const navigate = useNavigate();
  const [isSyncing, setIsSyncing] = useState<string | null>(null);
  const [deleteAccount, setDeleteAccount] = useState<InstagramAccount | null>(null);
  const [showConnectModal, setShowConnectModal] = useState(false);

  const fetchAccounts = useCallback(() => instagramAccountApi.list(), []);
  const { data: accounts, loading, error, refresh } = useFetch(fetchAccounts);

  const handleSync = async (account: InstagramAccount) => {
    setIsSyncing(account.id);
    try {
      await instagramAccountApi.sync(account.id);
      toast.success(`Conta @${account.username} sincronizada!`);
      refresh();
    } catch (err) {
      toast.error('Erro ao sincronizar conta');
    } finally {
      setIsSyncing(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteAccount) return;
    try {
      await instagramAccountApi.delete(deleteAccount.id);
      toast.success('Conta removida com sucesso');
      refresh();
    } catch (err) {
      toast.error('Erro ao remover conta');
    } finally {
      setDeleteAccount(null);
    }
  };

  const handleConnect = () => {
    // Abre popup de autenticação do Facebook/Instagram
    const clientId = import.meta.env.VITE_FACEBOOK_APP_ID;
    const redirectUri = `${window.location.origin}/instagram/callback`;
    const scope = 'instagram_basic,instagram_content_publish,instagram_shopping_tag_product,pages_read_engagement';
    
    const authUrl = `https://www.facebook.com/v18.0/dialog/oauth?client_id=${clientId}&redirect_uri=${redirectUri}&scope=${scope}&response_type=code`;
    
    window.open(authUrl, 'instagram_auth', 'width=600,height=700');
    setShowConnectModal(false);
  };

  if (loading) {
    return (
      <div className="p-6">
        <Loading message="Carregando contas..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Card>
          <div className="text-center py-8">
            <p className="text-red-500 mb-4">Erro ao carregar contas</p>
            <Button onClick={refresh} variant="primary">Tentar novamente</Button>
          </div>
        </Card>
      </div>
    );
  }

  const activeAccounts = accounts?.filter(a => a.is_active) || [];
  const totalFollowers = activeAccounts.reduce((sum, a) => sum + a.followers_count, 0);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Instagram
          </h1>
          <p className="text-gray-500 dark:text-gray-400">
            Gerencie contas, posts, stories e lives
          </p>
        </div>
        <Button
          onClick={() => setShowConnectModal(true)}
          variant="primary"
          leftIcon={<PlusIcon className="w-5 h-5" />}
        >
          Conectar Conta
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          title="Contas Conectadas"
          value={activeAccounts.length}
          icon={<CameraIcon className="w-5 h-5" />}
        />
        <StatCard
          title="Total de Seguidores"
          value={totalFollowers.toLocaleString('pt-BR')}
          icon={<ChartBarIcon className="w-5 h-5" />}
        />
        <StatCard
          title="Contas Verificadas"
          value={activeAccounts.filter(a => a.is_verified).length}
          icon={<CheckCircleIcon className="w-5 h-5 text-blue-500" />}
        />
        <StatCard
          title="Mídias Totais"
          value={activeAccounts.reduce((sum, a) => sum + a.media_count, 0).toLocaleString('pt-BR')}
          icon={<EyeIcon className="w-5 h-5" />}
        />
      </div>

      {/* Accounts List */}
      <Card>
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold">Contas Conectadas</h2>
        </div>
        
        {!accounts || accounts.length === 0 ? (
          <div className="p-8 text-center">
            <CameraIcon className="w-16 h-16 mx-auto text-gray-400 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Nenhuma conta conectada
            </h3>
            <p className="text-gray-500 mb-4">
              Conecte sua conta do Instagram para começar
            </p>
            <Button
              onClick={() => setShowConnectModal(true)}
              variant="primary"
              leftIcon={<PlusIcon className="w-5 h-5" />}
            >
              Conectar Instagram
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {accounts.map((account) => (
              <div
                key={account.id}
                className="p-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                <div className="flex items-start gap-4">
                  {/* Avatar */}
                  <div className="flex-shrink-0">
                    {account.profile_picture_url ? (
                      <img
                        src={account.profile_picture_url}
                        alt={account.username}
                        className="w-16 h-16 rounded-full object-cover"
                      />
                    ) : (
                      <div className="w-16 h-16 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                        <span className="text-2xl text-white font-bold">
                          {account.username[0].toUpperCase()}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                        @{account.username}
                      </h3>
                      {account.is_verified && (
                        <CheckCircleIcon className="w-5 h-5 text-blue-500" />
                      )}
                      {!account.is_active && (
                        <Badge variant="danger">Inativa</Badge>
                      )}
                    </div>
                    
                    <p className="text-gray-600 dark:text-gray-400 text-sm mt-1 line-clamp-2">
                      {account.biography || 'Sem biografia'}
                    </p>
                    
                    {/* Stats */}
                    <div className="flex flex-wrap gap-4 mt-3 text-sm">
                      <span className="text-gray-600 dark:text-gray-400">
                        <strong className="text-gray-900 dark:text-white">
                          {account.followers_count.toLocaleString('pt-BR')}
                        </strong>{' '}
                        seguidores
                      </span>
                      <span className="text-gray-600 dark:text-gray-400">
                        <strong className="text-gray-900 dark:text-white">
                          {account.follows_count.toLocaleString('pt-BR')}
                        </strong>{' '}
                        seguindo
                      </span>
                      <span className="text-gray-600 dark:text-gray-400">
                        <strong className="text-gray-900 dark:text-white">
                          {account.media_count.toLocaleString('pt-BR')}
                        </strong>{' '}
                        publicações
                      </span>
                    </div>
                    
                    {account.last_sync_at && (
                      <p className="text-xs text-gray-400 mt-2">
                        Sincronizado{' '}
                        {formatDistanceToNow(new Date(account.last_sync_at), {
                          addSuffix: true,
                          locale: ptBR,
                        })}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col gap-2">
                    <Button
                      onClick={() => navigate(`/instagram/${account.id}`)}
                      variant="secondary"
                      size="sm"
                      leftIcon={<EyeIcon className="w-4 h-4" />}
                    >
                      Ver
                    </Button>
                    <Button
                      onClick={() => handleSync(account)}
                      variant="secondary"
                      size="sm"
                      isLoading={isSyncing === account.id}
                      leftIcon={<ArrowPathIcon className="w-4 h-4" />}
                    >
                      Sincronizar
                    </Button>
                    <Button
                      onClick={() => setDeleteAccount(account)}
                      variant="danger"
                      size="sm"
                      leftIcon={<TrashIcon className="w-4 h-4" />}
                    >
                      Remover
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Connect Modal */}
      <Modal
        isOpen={showConnectModal}
        onClose={() => setShowConnectModal(false)}
        title="Conectar Conta do Instagram"
        size="md"
      >
        <div className="p-6">
          <div className="text-center">
            <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-purple-500 via-pink-500 to-orange-400 flex items-center justify-center">
              <CameraIcon className="w-10 h-10 text-white" />
            </div>
            
            <h3 className="text-lg font-semibold mb-2">
              Conectar Instagram
            </h3>
            
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Você será redirecionado para o Facebook para autorizar o acesso à sua conta do Instagram.
            </p>
            
            <div className="space-y-3">
              <Button
                onClick={handleConnect}
                variant="primary"
                className="w-full"
              >
                Continuar com Facebook
              </Button>
              
              <Button
                onClick={() => setShowConnectModal(false)}
                variant="ghost"
                className="w-full"
              >
                Cancelar
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation */}
      <Modal
        isOpen={!!deleteAccount}
        onClose={() => setDeleteAccount(null)}
        title="Remover Conta"
        size="sm"
      >
        <div className="p-6">
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            Tem certeza que deseja remover a conta{' '}
            <strong>@{deleteAccount?.username}</strong>? Esta ação não pode ser desfeita.
          </p>
          
          <div className="flex gap-3">
            <Button
              onClick={() => setDeleteAccount(null)}
              variant="ghost"
              className="flex-1"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleDelete}
              variant="danger"
              className="flex-1"
            >
              Remover
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default InstagramAccountsPage;
