import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlusIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Table, StatusBadge, ConfirmModal, PageLoading, PageTitle } from '../../components/common';
import { whatsappService, getErrorMessage } from '../../services';
import { useAccountStore } from '../../stores/accountStore';
import { WhatsAppAccount } from '../../types';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';

export const AccountsPage: React.FC = () => {
  const navigate = useNavigate();
  const { accounts, setAccounts, setLoading, isLoading, updateAccount, removeAccount } = useAccountStore();
  const [deleteModal, setDeleteModal] = useState<{ isOpen: boolean; account: WhatsAppAccount | null }>({
    isOpen: false,
    account: null,
  });
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    loadAccounts();
  }, []);

  const loadAccounts = async () => {
    setLoading(true);
    try {
      const response = await whatsappService.getAccounts();
      setAccounts(response.results);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const handleToggleStatus = async (account: WhatsAppAccount) => {
    try {
      const updated = account.status === 'active'
        ? await whatsappService.deactivateAccount(account.id)
        : await whatsappService.activateAccount(account.id);
      updateAccount(updated);
      toast.success(`Conta ${updated.status === 'active' ? 'ativada' : 'desativada'} com sucesso!`);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const handleSyncTemplates = async (account: WhatsAppAccount) => {
    try {
      const result = await whatsappService.syncTemplates(account.id);
      toast.success(result.message);
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const handleDelete = async () => {
    if (!deleteModal.account) return;
    setIsDeleting(true);
    try {
      await whatsappService.deleteAccount(deleteModal.account.id);
      removeAccount(deleteModal.account.id);
      toast.success('Conta removida com sucesso!');
      setDeleteModal({ isOpen: false, account: null });
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsDeleting(false);
    }
  };

  const columns = [
    {
      key: 'name',
      header: 'Nome',
      render: (account: WhatsAppAccount) => (
        <div>
          <p className="font-medium text-gray-900 dark:text-white">{account.name}</p>
          <p className="text-sm text-gray-500 dark:text-zinc-400">{account.display_phone_number || account.phone_number}</p>
        </div>
      ),
    },
    {
      key: 'phone_number_id',
      header: 'Phone Number ID',
      render: (account: WhatsAppAccount) => (
        <span className="text-sm font-mono text-gray-600 dark:text-zinc-400">{account.phone_number_id}</span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (account: WhatsAppAccount) => <StatusBadge status={account.status} />,
    },
    {
      key: 'auto_response',
      header: 'Resposta Auto',
      render: (account: WhatsAppAccount) => (
        <span className={`text-sm ${account.auto_response_enabled ? 'text-green-600' : 'text-gray-400'}`}>
          {account.auto_response_enabled ? 'Ativada' : 'Desativada'}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Criado em',
      render: (account: WhatsAppAccount) => (
        <span className="text-sm text-gray-600 dark:text-zinc-400">
          {format(new Date(account.created_at), "dd/MM/yyyy", { locale: ptBR })}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Ações',
      render: (account: WhatsAppAccount) => (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              handleToggleStatus(account);
            }}
          >
            {account.status === 'active' ? 'Desativar' : 'Ativar'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              handleSyncTemplates(account);
            }}
            leftIcon={<ArrowPathIcon className="w-4 h-4" />}
          >
            Sync
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteModal({ isOpen: true, account });
            }}
          >
            Excluir
          </Button>
        </div>
      ),
    },
  ];

  if (isLoading) {
    return <PageLoading />;
  }

  return (
    <div className="p-6">
      <PageTitle
        title="Contas WhatsApp"
        subtitle={`${accounts.length} conta(s) cadastrada(s)`}
        actions={
          <Button
            leftIcon={<PlusIcon className="w-5 h-5" />}
            onClick={() => navigate('/accounts/new')}
          >
            Nova Conta
          </Button>
        }
      />

      <Card noPadding>
        <Table
          columns={columns}
          data={accounts}
          keyExtractor={(account) => account.id}
          onRowClick={(account) => navigate(`/accounts/${account.id}`)}
          emptyMessage="Nenhuma conta cadastrada"
        />
      </Card>

      <ConfirmModal
        isOpen={deleteModal.isOpen}
        onClose={() => setDeleteModal({ isOpen: false, account: null })}
        onConfirm={handleDelete}
        title="Excluir Conta"
        message={`Tem certeza que deseja excluir a conta "${deleteModal.account?.name}"? Esta ação não pode ser desfeita.`}
        confirmText="Excluir"
        isLoading={isDeleting}
      />
    </div>
  );
};
