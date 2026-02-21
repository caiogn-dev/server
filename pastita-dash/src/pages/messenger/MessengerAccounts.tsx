import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Chip,
  Tooltip,
  Alert,
  CircularProgress,
  Grid,
  InputAdornment,
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Chat as ChatIcon,
  Search as SearchIcon,
} from '@mui/icons-material';
import { messengerService, MessengerAccount } from '../../services/messenger';

export default function MessengerAccounts() {
  const [accounts, setAccounts] = useState<MessengerAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<MessengerAccount | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    page_id: '',
    page_name: '',
    page_access_token: '',
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadAccounts();
  }, []);

  const loadAccounts = async () => {
    try {
      setLoading(true);
      const response = await messengerService.getAccounts();
      setAccounts(response.data || []);
      setError(null);
    } catch (err) {
      console.error('Error loading accounts:', err);
      setError('Erro ao carregar contas do Messenger');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenDialog = (account?: MessengerAccount) => {
    if (account) {
      setEditingAccount(account);
      setFormData({
        name: account.name || account.page_name,
        page_id: account.page_id,
        page_name: account.page_name,
        page_access_token: '',
      });
    } else {
      setEditingAccount(null);
      setFormData({
        name: '',
        page_id: '',
        page_name: '',
        page_access_token: '',
      });
    }
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    setEditingAccount(null);
    setFormData({
      name: '',
      page_id: '',
      page_name: '',
      page_access_token: '',
    });
  };

  const handleSubmit = async () => {
    try {
      setSubmitting(true);
      if (editingAccount) {
        await messengerService.updateAccount(editingAccount.id, formData);
      } else {
        await messengerService.createAccount(formData);
      }
      handleCloseDialog();
      loadAccounts();
    } catch (err) {
      console.error('Error saving account:', err);
      setError('Erro ao salvar conta');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Tem certeza que deseja excluir esta conta?')) return;
    
    try {
      await messengerService.deleteAccount(id);
      loadAccounts();
    } catch (err) {
      console.error('Error deleting account:', err);
      setError('Erro ao excluir conta');
    }
  };

  const handleVerifyWebhook = async (id: string) => {
    try {
      await messengerService.verifyWebhook(id);
      loadAccounts();
    } catch (err) {
      console.error('Error verifying webhook:', err);
      setError('Erro ao verificar webhook');
    }
  };

  const filteredAccounts = accounts.filter((acc) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      acc.page_name?.toLowerCase().includes(query) ||
      acc.page_id?.toLowerCase().includes(query)
    );
  });

  return (
    <Box p={3}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" fontWeight="bold">
          Contas do Messenger
        </Typography>
        <Box display="flex" gap={2}>
          <TextField
            size="small"
            placeholder="Buscar contas..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            }}
          />
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => handleOpenDialog()}
          >
            Adicionar Conta
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box display="flex" justifyContent="center" py={8}>
          <CircularProgress />
        </Box>
      ) : filteredAccounts.length === 0 ? (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 8 }}>
            <ChatIcon sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              Nenhuma conta configurada
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Adicione uma página do Facebook para começar a receber mensagens
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => handleOpenDialog()}
            >
              Adicionar Conta
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {filteredAccounts.map((account) => (
            <Grid item xs={12} md={6} lg={4} key={account.id}>
              <Card>
                <CardContent>
                  <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={2}>
                    <Box>
                      <Typography variant="h6" fontWeight="bold">
                        {account.page_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        ID: {account.page_id}
                      </Typography>
                    </Box>
                    <Box display="flex" gap={1}>
                      <Tooltip title="Editar">
                        <IconButton
                          size="small"
                          onClick={() => handleOpenDialog(account)}
                        >
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Excluir">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => handleDelete(account.id)}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </Box>

                  <Box display="flex" gap={1} mb={2}>
                    <Chip
                      size="small"
                      icon={account.is_active ? <CheckCircleIcon /> : <ErrorIcon />}
                      label={account.is_active ? 'Ativo' : 'Inativo'}
                      color={account.is_active ? 'success' : 'default'}
                    />
                    <Chip
                      size="small"
                      icon={account.webhook_verified ? <CheckCircleIcon /> : <ErrorIcon />}
                      label={account.webhook_verified ? 'Webhook OK' : 'Webhook Pendente'}
                      color={account.webhook_verified ? 'success' : 'warning'}
                    />
                  </Box>

                  {!account.webhook_verified && (
                    <Button
                      fullWidth
                      variant="outlined"
                      size="small"
                      startIcon={<RefreshIcon />}
                      onClick={() => handleVerifyWebhook(account.id)}
                    >
                      Verificar Webhook
                    </Button>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {/* Dialog */}
      <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingAccount ? 'Editar Conta' : 'Adicionar Conta do Messenger'}
        </DialogTitle>
        <DialogContent>
          <Box display="flex" flexDirection="column" gap={2} mt={1}>
            <TextField
              label="Nome da Conta"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              fullWidth
              required
              helperText="Nome para identificar esta conta no painel"
            />

            <TextField
              label="Page ID"
              value={formData.page_id}
              onChange={(e) => setFormData({ ...formData, page_id: e.target.value })}
              fullWidth
              required
              disabled={!!editingAccount}
            />
            
            <TextField
              label="Nome da Página"
              value={formData.page_name}
              onChange={(e) => setFormData({ ...formData, page_name: e.target.value })}
              fullWidth
              required
            />
            
            <TextField
              label="Page Access Token"
              value={formData.page_access_token}
              onChange={(e) => setFormData({ ...formData, page_access_token: e.target.value })}
              fullWidth
              required
              type="password"
              helperText="Token de acesso da página do Facebook"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={submitting || !formData.name || !formData.page_id || !formData.page_name || !formData.page_access_token}
          >
            {submitting ? <CircularProgress size={24} /> : 'Salvar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
