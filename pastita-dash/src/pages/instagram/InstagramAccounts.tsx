// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  IconButton,
  Avatar,
  Chip,
  Grid,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Switch,
  FormControlLabel,
  Alert,
  Tooltip,
  CircularProgress,
  Divider,
  Snackbar,
} from '@mui/material';
import InstagramIcon from '@mui/icons-material/Instagram';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import SettingsIcon from '@mui/icons-material/Settings';
import DeleteIcon from '@mui/icons-material/Delete';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import WarningIcon from '@mui/icons-material/Warning';
import ErrorIcon from '@mui/icons-material/Error';
import MessageIcon from '@mui/icons-material/Message';
import PeopleIcon from '@mui/icons-material/People';
import KeyIcon from '@mui/icons-material/Key';
import SyncIcon from '@mui/icons-material/Sync';
import { instagramService, InstagramAccount, CreateInstagramAccount, InstagramAccountStats } from '../../services/instagram';

const statusConfig: Record<string, { color: 'success' | 'warning' | 'error' | 'default'; icon: React.ReactNode; label: string }> = {
  active: { color: 'success', icon: <CheckCircleIcon fontSize="small" />, label: 'Ativo' },
  inactive: { color: 'default', icon: <WarningIcon fontSize="small" />, label: 'Inativo' },
  pending: { color: 'warning', icon: <WarningIcon fontSize="small" />, label: 'Pendente' },
  suspended: { color: 'error', icon: <ErrorIcon fontSize="small" />, label: 'Suspenso' },
  expired: { color: 'error', icon: <ErrorIcon fontSize="small" />, label: 'Token Expirado' },
};

export default function InstagramAccounts() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [accounts, setAccounts] = useState<InstagramAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState<InstagramAccount | null>(null);
  const [stats, setStats] = useState<Record<string, InstagramAccountStats>>({});
  const [syncing, setSyncing] = useState<string | null>(null);
  const [formData, setFormData] = useState<Partial<CreateInstagramAccount>>({
    name: '',
    instagram_account_id: '',
    instagram_user_id: '',
    facebook_page_id: '',
    username: '',
    app_id: '955411496814093',
    app_secret: '',
    access_token: '',
    webhook_verify_token: 'pastita-ig-verify',
    messaging_enabled: true,
    auto_response_enabled: false,
  });
  const [saving, setSaving] = useState(false);

  // Handle OAuth callback
  useEffect(() => {
    const oauthSuccess = searchParams.get('oauth_success');
    const oauthError = searchParams.get('error');
    const oauthData = searchParams.get('data');
    
    if (oauthSuccess === 'true' && oauthData) {
      try {
        // Decode base64url data from OAuth callback (replace URL-safe chars)
        const base64 = oauthData.replace(/-/g, '+').replace(/_/g, '/');
        // Add padding if needed
        const padded = base64 + '=='.slice(0, (4 - base64.length % 4) % 4);
        const decodedData = JSON.parse(atob(padded));
        console.log('OAuth data received:', decodedData);
        
        // Pre-fill form with OAuth data
        setFormData(prev => ({
          ...prev,
          name: decodedData.username || '',
          instagram_account_id: decodedData.instagram_account_id || decodedData.instagram_user_id || '',
          instagram_user_id: decodedData.instagram_user_id || '',
          username: decodedData.username || '',
          access_token: decodedData.access_token || '',
        }));
        
        setSuccess(`Conta @${decodedData.username} autorizada! Complete o cadastro abaixo.`);
        setDialogOpen(true);
        
        // Clear URL params
        setSearchParams({});
      } catch (err) {
        console.error('Error parsing OAuth data:', err);
        setError('Erro ao processar dados de autenticação');
        setSearchParams({});
      }
    } else if (oauthError) {
      setError(`Erro na autenticação: ${oauthError}`);
      setSearchParams({});
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    loadAccounts();
  }, []);

  const loadAccounts = async () => {
    try {
      setLoading(true);
      const response = await instagramService.getAccounts();
      setAccounts(response.data?.results || []);
      
      // Load stats for each account
      const statsPromises = (response.data?.results || []).map(async (account: InstagramAccount) => {
        try {
          const statsRes = await instagramService.getAccountStats(account.id);
          return { id: account.id, stats: statsRes.data };
        } catch {
          return { id: account.id, stats: null };
        }
      });
      
      const statsResults = await Promise.all(statsPromises);
      const statsMap: Record<string, InstagramAccountStats> = {};
      statsResults.forEach(({ id, stats: accountStats }) => {
        if (accountStats) statsMap[id] = accountStats;
      });
      setStats(statsMap);
      
      setError(null);
    } catch (err) {
      console.error('Error loading accounts:', err);
      setError('Erro ao carregar contas do Instagram');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAccount = async () => {
    try {
      setSaving(true);
      await instagramService.createAccount(formData as CreateInstagramAccount);
      setDialogOpen(false);
      setFormData({
        name: '',
        instagram_account_id: '',
        instagram_user_id: '',
        facebook_page_id: '',
        username: '',
        app_id: '955411496814093',
        app_secret: '',
        access_token: '',
        webhook_verify_token: 'pastita-ig-verify',
        messaging_enabled: true,
        auto_response_enabled: false,
      });
      loadAccounts();
    } catch (err) {
      console.error('Error creating account:', err);
      setError('Erro ao criar conta');
    } finally {
      setSaving(false);
    }
  };

  const handleRefreshToken = async (account: InstagramAccount) => {
    try {
      await instagramService.refreshToken(account.id);
      loadAccounts();
    } catch (err) {
      console.error('Error refreshing token:', err);
      setError('Erro ao atualizar token');
    }
  };

  const handleSyncProfile = async (account: InstagramAccount) => {
    try {
      await instagramService.syncProfile(account.id);
      loadAccounts();
    } catch (err) {
      console.error('Error syncing profile:', err);
      setError('Erro ao sincronizar perfil');
    }
  };

  const handleDeleteAccount = async (account: InstagramAccount) => {
    if (!confirm(`Deseja realmente excluir a conta @${account.username}?`)) return;
    
    try {
      await instagramService.deleteAccount(account.id);
      loadAccounts();
    } catch (err) {
      console.error('Error deleting account:', err);
      setError('Erro ao excluir conta');
    }
  };

  const handleSyncConversations = async (account: InstagramAccount) => {
    try {
      setSyncing(account.id);
      const result = await instagramService.syncConversations(account.id);
      setSuccess(`Sincronizado: ${result.data?.count || 0} conversas encontradas`);
      loadAccounts();
    } catch (err) {
      console.error('Error syncing conversations:', err);
      setError('Erro ao sincronizar conversas');
    } finally {
      setSyncing(null);
    }
  };

  const handleConnectInstagram = () => {
    // Redirect to Instagram OAuth via backend endpoint
    // Using short URI: /ig/start which handles all OAuth params
    const backendUrl = import.meta.env.VITE_API_URL?.replace('/api/v1', '') || 'https://backend.pastita.com.br';
    window.location.href = `${backendUrl}/ig/start`;
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box display="flex" alignItems="center" gap={2}>
          <InstagramIcon sx={{ fontSize: 40, color: '#E4405F' }} />
          <Box>
            <Typography variant="h4" fontWeight="bold">
              Instagram
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Gerencie suas contas e mensagens do Instagram
            </Typography>
          </Box>
        </Box>
        <Box display="flex" gap={2}>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={loadAccounts}
          >
            Atualizar
          </Button>
          <Button
            variant="outlined"
            startIcon={<AddIcon />}
            onClick={() => setDialogOpen(true)}
          >
            Adicionar Manual
          </Button>
          <Button
            variant="contained"
            startIcon={<InstagramIcon />}
            onClick={handleConnectInstagram}
            sx={{
              background: 'linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)',
              '&:hover': {
                background: 'linear-gradient(45deg, #e6683c, #dc2743, #cc2366, #bc1888, #f09433)',
              },
            }}
          >
            Conectar via Instagram
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      
      {success && (
        <Alert severity="success" sx={{ mb: 3 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Accounts Grid */}
      {accounts.length === 0 ? (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 6 }}>
            <InstagramIcon sx={{ fontSize: 80, color: '#E4405F', opacity: 0.5, mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              Nenhuma conta conectada
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Conecte sua conta do Instagram Business para começar a gerenciar mensagens
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setDialogOpen(true)}
              sx={{
                background: 'linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)',
              }}
            >
              Conectar Primeira Conta
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {accounts.map((account) => {
            const status = statusConfig[account.status] || statusConfig.inactive;
            const accountStats = stats[account.id];
            
            return (
              <Grid item xs={12} md={6} lg={4} key={account.id}>
                <Card
                  sx={{
                    height: '100%',
                    position: 'relative',
                    '&:hover': { boxShadow: 6 },
                  }}
                >
                  <CardContent>
                    {/* Account Header */}
                    <Box display="flex" alignItems="center" gap={2} mb={2}>
                      <Avatar
                        src={account.profile_picture_url}
                        sx={{ width: 60, height: 60 }}
                      >
                        <InstagramIcon />
                      </Avatar>
                      <Box flex={1}>
                        <Typography variant="h6" fontWeight="bold">
                          {account.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          @{account.username}
                        </Typography>
                      </Box>
                      <Chip
                        icon={status.icon as React.ReactElement}
                        label={status.label}
                        color={status.color}
                        size="small"
                      />
                    </Box>

                    <Divider sx={{ my: 2 }} />

                    {/* Stats */}
                    {accountStats && (
                      <Grid container spacing={2} mb={2}>
                        <Grid item xs={6}>
                          <Box display="flex" alignItems="center" gap={1}>
                            <PeopleIcon fontSize="small" color="action" />
                            <Box>
                              <Typography variant="caption" color="text.secondary">
                                Conversas
                              </Typography>
                              <Typography variant="body2" fontWeight="bold">
                                {accountStats.active_conversations}
                              </Typography>
                            </Box>
                          </Box>
                        </Grid>
                        <Grid item xs={6}>
                          <Box display="flex" alignItems="center" gap={1}>
                            <MessageIcon fontSize="small" color="action" />
                            <Box>
                              <Typography variant="caption" color="text.secondary">
                                Mensagens
                              </Typography>
                              <Typography variant="body2" fontWeight="bold">
                                {accountStats.total_messages}
                              </Typography>
                            </Box>
                          </Box>
                        </Grid>
                      </Grid>
                    )}

                    {/* Info */}
                    <Box mb={2}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Seguidores: {account.followers_count?.toLocaleString() || 'N/A'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Token: {account.masked_token}
                      </Typography>
                      {account.token_expires_at && (
                        <Typography variant="caption" color="text.secondary" display="block">
                          Expira: {new Date(account.token_expires_at).toLocaleDateString('pt-BR')}
                        </Typography>
                      )}
                    </Box>

                    {/* Features */}
                    <Box display="flex" gap={1} flexWrap="wrap" mb={2}>
                      {account.messaging_enabled && (
                        <Chip label="Mensagens" size="small" color="primary" variant="outlined" />
                      )}
                      {account.auto_response_enabled && (
                        <Chip label="Auto-resposta" size="small" color="secondary" variant="outlined" />
                      )}
                    </Box>

                    {/* Actions */}
                    <Box display="flex" justifyContent="space-between">
                      <Box>
                        <Tooltip title="Sincronizar Conversas">
                          <IconButton 
                            onClick={() => handleSyncConversations(account)} 
                            size="small"
                            disabled={syncing === account.id}
                            color="primary"
                          >
                            {syncing === account.id ? <CircularProgress size={20} /> : <SyncIcon />}
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Sincronizar Perfil">
                          <IconButton onClick={() => handleSyncProfile(account)} size="small">
                            <RefreshIcon />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Atualizar Token">
                          <IconButton onClick={() => handleRefreshToken(account)} size="small">
                            <KeyIcon />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Configurações">
                          <IconButton onClick={() => setSelectedAccount(account)} size="small">
                            <SettingsIcon />
                          </IconButton>
                        </Tooltip>
                      </Box>
                      <Tooltip title="Excluir">
                        <IconButton
                          onClick={() => handleDeleteAccount(account)}
                          size="small"
                          color="error"
                        >
                          <DeleteIcon />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}

      {/* Create Account Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Box display="flex" alignItems="center" gap={2}>
            <InstagramIcon sx={{ color: '#E4405F' }} />
            Conectar Conta do Instagram
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 3, mt: 1 }}>
            Para conectar sua conta, você precisa ter uma conta Instagram Business conectada a uma Página do Facebook e um App configurado no Meta Developer Console.
          </Alert>
          
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Nome da Conta"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Ex: Pastita Instagram"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Username"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                placeholder="@seuusuario"
                InputProps={{ startAdornment: '@' }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Instagram Account ID"
                value={formData.instagram_account_id}
                onChange={(e) => setFormData({ ...formData, instagram_account_id: e.target.value })}
                placeholder="ID da conta Instagram"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Instagram User ID"
                value={formData.instagram_user_id}
                onChange={(e) => setFormData({ ...formData, instagram_user_id: e.target.value })}
                placeholder="ID do usuário Instagram"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Facebook Page ID"
                value={formData.facebook_page_id}
                onChange={(e) => setFormData({ ...formData, facebook_page_id: e.target.value })}
                placeholder="ID da página do Facebook"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="App ID"
                value={formData.app_id}
                onChange={(e) => setFormData({ ...formData, app_id: e.target.value })}
                placeholder="ID do App no Meta"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="App Secret"
                type="password"
                value={formData.app_secret}
                onChange={(e) => setFormData({ ...formData, app_secret: e.target.value })}
                placeholder="Secret do App"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Access Token"
                multiline
                rows={3}
                value={formData.access_token}
                onChange={(e) => setFormData({ ...formData, access_token: e.target.value })}
                placeholder="Token de acesso de longa duração"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.messaging_enabled}
                    onChange={(e) => setFormData({ ...formData, messaging_enabled: e.target.checked })}
                  />
                }
                label="Habilitar Mensagens"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.auto_response_enabled}
                    onChange={(e) => setFormData({ ...formData, auto_response_enabled: e.target.checked })}
                  />
                }
                label="Habilitar Auto-resposta"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={handleCreateAccount}
            disabled={saving || !formData.name || !formData.instagram_account_id || !formData.access_token}
            sx={{
              background: 'linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)',
            }}
          >
            {saving ? <CircularProgress size={24} /> : 'Conectar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
