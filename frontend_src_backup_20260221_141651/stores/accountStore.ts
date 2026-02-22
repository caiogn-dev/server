import { create } from 'zustand';
import { WhatsAppAccount } from '../types';

interface AccountState {
  accounts: WhatsAppAccount[];
  selectedAccount: WhatsAppAccount | null;
  isLoading: boolean;
  setAccounts: (accounts: WhatsAppAccount[]) => void;
  setSelectedAccount: (account: WhatsAppAccount | null) => void;
  setLoading: (loading: boolean) => void;
  updateAccount: (account: WhatsAppAccount) => void;
  removeAccount: (id: string) => void;
}

export const useAccountStore = create<AccountState>((set) => ({
  accounts: [],
  selectedAccount: null,
  isLoading: false,
  setAccounts: (accounts) => set({ accounts }),
  setSelectedAccount: (account) => set({ selectedAccount: account }),
  setLoading: (isLoading) => set({ isLoading }),
  updateAccount: (account) =>
    set((state) => ({
      accounts: state.accounts.map((a) => (a.id === account.id ? account : a)),
      selectedAccount: state.selectedAccount?.id === account.id ? account : state.selectedAccount,
    })),
  removeAccount: (id) =>
    set((state) => ({
      accounts: state.accounts.filter((a) => a.id !== id),
      selectedAccount: state.selectedAccount?.id === id ? null : state.selectedAccount,
    })),
}));
