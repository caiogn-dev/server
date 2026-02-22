import React, { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Card, Button, Input, Loading, PageTitle } from '../../components/common';
import { authService, getErrorMessage, notificationsService } from '../../services';
import { NotificationPreference } from '../../services/notifications';
import { useAuthStore } from '../../stores/authStore';

type NotificationSection = {
  id: string;
  title: string;
  description: string;
  enabledKey: keyof NotificationPreference;
  options: Array<{
    key: keyof NotificationPreference;
    label: string;
    description: string;
  }>;
};

type ToggleProps = {
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  label: string;
};

const Toggle: React.FC<ToggleProps> = ({ checked, onChange, disabled = false, label }) => (
  <label
    className={`relative inline-flex items-center ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
  >
    <input
      type="checkbox"
      className="sr-only peer"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      disabled={disabled}
      aria-label={label}
    />
    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white dark:bg-zinc-900 after:border-gray-300 dark:border-zinc-700 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
  </label>
);

export const SettingsPage: React.FC = () => {
  const { user, setAuth } = useAuthStore();
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [isLoadingPreferences, setIsLoadingPreferences] = useState(true);
  const [isSavingPreferences, setIsSavingPreferences] = useState(false);
  const [preferences, setPreferences] = useState<NotificationPreference | null>(null);
  const [passwordForm, setPasswordForm] = useState({
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
  });

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      toast.error('As senhas não coincidem');
      return;
    }

    if (passwordForm.newPassword.length < 8) {
      toast.error('A nova senha deve ter pelo menos 8 caracteres');
      return;
    }

    setIsChangingPassword(true);
    try {
      const result = await authService.changePassword(
        passwordForm.oldPassword,
        passwordForm.newPassword
      );
      setAuth(result.token, user!);
      toast.success('Senha alterada com sucesso!');
      setPasswordForm({ oldPassword: '', newPassword: '', confirmPassword: '' });
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsChangingPassword(false);
    }
  };

  const loadPreferences = async () => {
    setIsLoadingPreferences(true);
    try {
      const data = await notificationsService.getPreferences();
      setPreferences(data);
    } catch (error) {
      toast.error('Não foi possível carregar as preferências de notificação');
    } finally {
      setIsLoadingPreferences(false);
    }
  };

  useEffect(() => {
    loadPreferences();
  }, []);

  const handlePreferenceChange = (key: keyof NotificationPreference, value: boolean) => {
    setPreferences((prev) => {
      if (!prev) return prev;
      const updated = { ...prev, [key]: value };

      if (key === 'email_enabled' && !value) {
        updated.email_messages = false;
        updated.email_orders = false;
        updated.email_payments = false;
        updated.email_system = false;
      }

      if (key === 'push_enabled' && !value) {
        updated.push_messages = false;
        updated.push_orders = false;
        updated.push_payments = false;
        updated.push_system = false;
      }

      if (key === 'inapp_enabled' && !value) {
        updated.inapp_sound = false;
      }

      return updated;
    });
  };

  const handleSavePreferences = async () => {
    if (!preferences) return;
    setIsSavingPreferences(true);
    try {
      const updated = await notificationsService.updatePreferences(preferences);
      setPreferences(updated);
      toast.success('Preferências de notificação salvas!');
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setIsSavingPreferences(false);
    }
  };

  const notificationSections: NotificationSection[] = [
    {
      id: 'email',
      title: 'Email',
      description: 'Alertas enviados para o email cadastrado.',
      enabledKey: 'email_enabled',
      options: [
        {
          key: 'email_messages',
          label: 'Mensagens',
          description: 'Novas mensagens e respostas do atendimento.',
        },
        {
          key: 'email_orders',
          label: 'Pedidos',
          description: 'Mudanças de status e atualizações de pedidos.',
        },
        {
          key: 'email_payments',
          label: 'Pagamentos',
          description: 'Confirmações, falhas e reembolsos.',
        },
        {
          key: 'email_system',
          label: 'Sistema',
          description: 'Avisos e alertas críticos do painel.',
        },
      ],
    },
    {
      id: 'push',
      title: 'Push',
      description: 'Notificações rápidas no navegador.',
      enabledKey: 'push_enabled',
      options: [
        {
          key: 'push_messages',
          label: 'Mensagens',
          description: 'Atualizações de conversas em tempo real.',
        },
        {
          key: 'push_orders',
          label: 'Pedidos',
          description: 'Novos pedidos e alterações de status.',
        },
        {
          key: 'push_payments',
          label: 'Pagamentos',
          description: 'Eventos de pagamento importantes.',
        },
        {
          key: 'push_system',
          label: 'Sistema',
          description: 'Alertas do sistema e incidentes.',
        },
      ],
    },
    {
      id: 'inapp',
      title: 'Painel',
      description: 'Alertas dentro do próprio dashboard.',
      enabledKey: 'inapp_enabled',
      options: [
        {
          key: 'inapp_sound',
          label: 'Som de notificação',
          description: 'Tocar som ao receber um novo alerta.',
        },
      ],
    },
  ];

  return (
    <div className="p-6 space-y-6">
      <PageTitle title="Configurações" subtitle="Gerencie suas preferências e segurança" />

      {/* User Info */}
      <Card title="Informações do Usuário">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-500 dark:text-zinc-400">Usuário</label>
            <p className="text-gray-900 dark:text-white">{user?.username}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-500 dark:text-zinc-400">Email</label>
            <p className="text-gray-900 dark:text-white">{user?.email || '-'}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-500 dark:text-zinc-400">Nome</label>
            <p className="text-gray-900 dark:text-white">{user?.first_name || '-'} {user?.last_name || ''}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-500 dark:text-zinc-400">Tipo</label>
            <p className="text-gray-900 dark:text-white">
              {user?.is_superuser ? 'Superusuário' : user?.is_staff ? 'Staff' : 'Usuário'}
            </p>
          </div>
        </div>
      </Card>

      {/* Change Password */}
      <Card title="Alterar Senha">
        <form onSubmit={handleChangePassword} className="space-y-4 max-w-md">
          <Input
            label="Senha Atual"
            type="password"
            required
            value={passwordForm.oldPassword}
            onChange={(e) => setPasswordForm({ ...passwordForm, oldPassword: e.target.value })}
          />
          <Input
            label="Nova Senha"
            type="password"
            required
            value={passwordForm.newPassword}
            onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
            helperText="Mínimo de 8 caracteres"
          />
          <Input
            label="Confirmar Nova Senha"
            type="password"
            required
            value={passwordForm.confirmPassword}
            onChange={(e) => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
          />
          <Button type="submit" isLoading={isChangingPassword}>
            Alterar Senha
          </Button>
        </form>
      </Card>

      {/* Notification Preferences */}
      <Card
        title="Preferências de Notificação"
        subtitle="Defina onde deseja receber alertas do sistema"
        actions={
          <Button
            onClick={handleSavePreferences}
            isLoading={isSavingPreferences}
            disabled={!preferences}
          >
            Salvar preferências
          </Button>
        }
      >
        {isLoadingPreferences ? (
          <div className="py-10">
            <Loading size="lg" />
            <p className="mt-3 text-center text-sm text-gray-500 dark:text-zinc-400">
              Carregando preferências...
            </p>
          </div>
        ) : !preferences ? (
          <div className="text-sm text-red-500">
            Não foi possível carregar as preferências de notificação.
          </div>
        ) : (
          <div className="space-y-6">
            {notificationSections.map((section) => {
              const isSectionEnabled = preferences[section.enabledKey];

              return (
                <div key={section.id} className="rounded-lg border border-gray-100 p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">{section.title}</p>
                      <p className="text-sm text-gray-500 dark:text-zinc-400">{section.description}</p>
                    </div>
                    <Toggle
                      label={`Ativar ${section.title}`}
                      checked={isSectionEnabled}
                      onChange={(value) => handlePreferenceChange(section.enabledKey, value)}
                    />
                  </div>
                  {section.options.length > 0 && (
                    <div className="mt-4 space-y-3">
                      {section.options.map((option) => (
                        <div key={option.key} className="flex items-center justify-between gap-4">
                          <div>
                            <p className="text-sm font-medium text-gray-800 dark:text-gray-200">{option.label}</p>
                            <p className="text-xs text-gray-500 dark:text-zinc-400">{option.description}</p>
                          </div>
                          <Toggle
                            label={`${section.title} - ${option.label}`}
                            checked={Boolean(preferences[option.key])}
                            onChange={(value) => handlePreferenceChange(option.key, value)}
                            disabled={!isSectionEnabled}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* API Info */}
      <Card title="Informações da API">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-500 dark:text-zinc-400">Base URL</label>
            <p className="text-gray-900 dark:text-white font-mono text-sm">
              {import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'}
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-500 dark:text-zinc-400">Documentação</label>
            <div className="flex gap-4 mt-1">
              <a
                href={`${import.meta.env.VITE_API_URL?.replace('/api/v1', '') || 'http://localhost:8000'}/api/docs/`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary-600 hover:text-primary-700"
              >
                Swagger UI
              </a>
              <a
                href={`${import.meta.env.VITE_API_URL?.replace('/api/v1', '') || 'http://localhost:8000'}/api/redoc/`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary-600 hover:text-primary-700"
              >
                ReDoc
              </a>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
};
