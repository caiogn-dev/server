/**
 * WhatsApp Chat Page - Dedicated full-page chat interface
 * 
 * Esta página fornece acesso direto ao ChatWindow do WhatsApp
 * para gerenciar conversas em tempo real.
 */
import React, { useEffect, useState } from 'react';
import { ChatWindow } from '../../components/chat';
import { useAccountStore } from '../../stores/accountStore';
import { Card } from '../../components/common';
import { 
  DevicePhoneMobileIcon, 
  ChatBubbleLeftRightIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import { Link } from 'react-router-dom';
import { whatsappService, getErrorMessage } from '../../services';
import toast from 'react-hot-toast';

export const WhatsAppChatPage: React.FC = () => {
  const { accounts, selectedAccount, setSelectedAccount, setAccounts } = useAccountStore();
  const [isLoading, setIsLoading] = useState(true);

  // Load accounts if not already loaded
  useEffect(() => {
    const loadAccounts = async () => {
      if (accounts.length === 0) {
        setIsLoading(true);
        try {
          const response = await whatsappService.getAccounts();
          setAccounts(response.results || []);
          // Select first account if none selected
          if (response.results?.length > 0 && !selectedAccount) {
            setSelectedAccount(response.results[0]);
          }
        } catch (error) {
          toast.error(getErrorMessage(error));
        } finally {
          setIsLoading(false);
        }
      } else {
        setIsLoading(false);
        // Select first account if none selected
        if (!selectedAccount && accounts.length > 0) {
          setSelectedAccount(accounts[0]);
        }
      }
    };

    loadAccounts();
  }, [accounts, selectedAccount, setAccounts, setSelectedAccount]);

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-8rem)]">
        <div className="flex flex-col items-center gap-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
          <p className="text-gray-500 dark:text-zinc-400">Carregando contas WhatsApp...</p>
        </div>
      </div>
    );
  }

  // No accounts state
  if (accounts.length === 0) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-8rem)]">
        <Card className="max-w-md text-center p-8">
          <div className="w-16 h-16 mx-auto mb-4 bg-amber-100 dark:bg-amber-900/30 rounded-full flex items-center justify-center">
            <ExclamationTriangleIcon className="w-8 h-8 text-amber-600 dark:text-amber-400" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            Nenhuma conta WhatsApp configurada
          </h2>
          <p className="text-gray-600 dark:text-zinc-400 mb-6">
            Você precisa configurar uma conta do WhatsApp Business para começar a enviar e receber mensagens.
          </p>
          <Link
            to="/accounts/new"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <PlusIcon className="w-5 h-5" />
            Adicionar Conta WhatsApp
          </Link>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      {/* Header with account selector */}
      <div className="flex items-center justify-between px-4 py-3 bg-white dark:bg-zinc-900 border-b border-gray-200 dark:border-zinc-800">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
            <DevicePhoneMobileIcon className="w-6 h-6 text-green-600 dark:text-green-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-white">
              WhatsApp Chat
            </h1>
            <p className="text-sm text-gray-500 dark:text-zinc-400">
              Gerencie suas conversas em tempo real
            </p>
          </div>
        </div>

        {/* Account Selector */}
        {accounts.length > 1 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-zinc-400">Conta:</span>
            <select
              value={selectedAccount?.id || ''}
              onChange={(e) => {
                const account = accounts.find(a => a.id === e.target.value);
                if (account) setSelectedAccount(account);
              }}
              className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-zinc-800 border border-gray-200 dark:border-zinc-700 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.phone_number} - {account.name || 'WhatsApp Business'}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Chat Window */}
      {selectedAccount ? (
        <div className="flex-1 overflow-hidden">
          <ChatWindow
            accountId={selectedAccount.id}
            accountName={selectedAccount.name || selectedAccount.phone_number}
          />
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center bg-gray-50 dark:bg-zinc-950">
          <div className="text-center">
            <ChatBubbleLeftRightIcon className="w-16 h-16 mx-auto text-gray-300 dark:text-zinc-700 mb-4" />
            <p className="text-gray-500 dark:text-zinc-400">
              Selecione uma conta para começar
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default WhatsAppChatPage;
