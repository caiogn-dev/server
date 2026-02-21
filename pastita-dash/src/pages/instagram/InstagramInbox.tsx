// @ts-nocheck
import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Card,
  Typography,
  TextField,
  IconButton,
  Avatar,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  ListItemButton,
  Badge,
  Chip,
  Divider,
  CircularProgress,
  InputAdornment,
  Paper,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Tooltip,
  Alert,
} from '@mui/material';
import InstagramIcon from '@mui/icons-material/Instagram';
import SendIcon from '@mui/icons-material/Send';
import SearchIcon from '@mui/icons-material/Search';
import ImageIcon from '@mui/icons-material/Image';
import RefreshIcon from '@mui/icons-material/Refresh';
import CircleIcon from '@mui/icons-material/Circle';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import DoneIcon from '@mui/icons-material/Done';
import DoneAllIcon from '@mui/icons-material/DoneAll';
import {
  instagramService,
  InstagramAccount,
  InstagramConversation,
  InstagramMessage,
} from '../../services/instagram';

const messageStatusIcon: Record<string, React.ReactNode> = {
  pending: <AccessTimeIcon fontSize="inherit" sx={{ color: 'text.disabled' }} />,
  sent: <DoneIcon fontSize="inherit" sx={{ color: 'text.disabled' }} />,
  delivered: <DoneAllIcon fontSize="inherit" sx={{ color: 'text.disabled' }} />,
  seen: <DoneAllIcon fontSize="inherit" sx={{ color: 'primary.main' }} />,
  failed: <CircleIcon fontSize="inherit" sx={{ color: 'error.main' }} />,
};

export default function InstagramInbox() {
  const [accounts, setAccounts] = useState<InstagramAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [conversations, setConversations] = useState<InstagramConversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<InstagramConversation | null>(null);
  const [messages, setMessages] = useState<InstagramMessage[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadAccounts();
  }, []);

  useEffect(() => {
    if (selectedAccountId) {
      loadConversations();
    }
  }, [selectedAccountId]);

  useEffect(() => {
    if (selectedConversation) {
      loadMessages();
    }
  }, [selectedConversation]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadAccounts = async () => {
    try {
      const response = await instagramService.getAccounts();
      // PaginatedResponse: response.data.results
      const results = response.data?.results || [];
      setAccounts(results);
      if (results.length > 0) {
        setSelectedAccountId(results[0].id);
      }
    } catch (err) {
      console.error('Error loading accounts:', err);
      setError('Erro ao carregar contas');
    } finally {
      setLoading(false);
    }
  };

  const loadConversations = async () => {
    if (!selectedAccountId) return;
    
    try {
      setLoading(true);
      const response = await instagramService.getConversations({
        account_id: selectedAccountId,
      });
      // PaginatedResponse: response.data.results
      setConversations(response.data?.results || []);
      setError(null);
    } catch (err) {
      console.error('Error loading conversations:', err);
      setError('Erro ao carregar conversas');
    } finally {
      setLoading(false);
    }
  };

  const loadMessages = async () => {
    if (!selectedConversation) return;
    
    try {
      setLoadingMessages(true);
      const response = await instagramService.getMessages({
        conversation_id: selectedConversation.id,
      });
      // PaginatedResponse: response.data.results
      const results = response.data?.results || [];
      setMessages(results.reverse());
      
      // Mark as seen - usa sender_id (quem enviou a última mensagem)
      if (selectedAccountId && selectedConversation.participant_id) {
        await instagramService.markSeen(selectedAccountId, selectedConversation.participant_id);
      }
    } catch (err) {
      console.error('Error loading messages:', err);
    } finally {
      setLoadingMessages(false);
    }
  };

  const handleSendMessage = async () => {
    if (!newMessage.trim() || !selectedConversation || !selectedAccountId) return;

    try {
      setSending(true);
      
      // Typing indicator (best effort - não falha se der erro)
      try {
        await instagramService.sendTyping(selectedAccountId, selectedConversation.participant_id);
      } catch {
        // Silently ignore typing errors
      }
      
      // Send message
      const response = await instagramService.sendMessage({
        account_id: selectedAccountId,
        recipient_id: selectedConversation.participant_id,
        text: newMessage.trim(),
      });
      
      // Adiciona mensagem enviada à lista
      const sentMessage = response.data;
      if (sentMessage) {
        setMessages((prev) => [...prev, sentMessage]);
      }
      setNewMessage('');
    } catch (err) {
      console.error('Error sending message:', err);
      setError('Erro ao enviar mensagem');
    } finally {
      setSending(false);
    }
  };

  const filteredConversations = conversations.filter((conv) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      conv.participant_username?.toLowerCase().includes(query) ||
      conv.participant_name?.toLowerCase().includes(query) ||
      conv.last_message_preview?.toLowerCase().includes(query)
    );
  });

  const formatTime = (dateStr: string | null | undefined) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) {
      return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
      return 'Ontem';
    } else if (diffDays < 7) {
      return date.toLocaleDateString('pt-BR', { weekday: 'short' });
    } else {
      return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
    }
  };

  // Helper para pegar o ícone de status com fallback
  const getStatusIcon = (status: string | undefined) => {
    if (!status) return null;
    return messageStatusIcon[status] || null;
  };

  return (
    <Box sx={{ display: 'flex', height: 'calc(100vh - 100px)', gap: 2, p: 2 }}>
      {/* Sidebar - Conversations List */}
      <Card sx={{ width: 360, display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <Box display="flex" alignItems="center" gap={2} mb={2}>
            <InstagramIcon sx={{ color: '#E4405F', fontSize: 28 }} />
            <Typography variant="h6" fontWeight="bold">
              Instagram DM
            </Typography>
            <Box flex={1} />
            <Tooltip title="Atualizar">
              <IconButton size="small" onClick={loadConversations}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
          
          {/* Account Selector */}
          {accounts.length > 1 && (
            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
              <InputLabel>Conta</InputLabel>
              <Select
                value={selectedAccountId}
                label="Conta"
                onChange={(e) => setSelectedAccountId(e.target.value)}
              >
                {accounts.map((account) => (
                  <MenuItem key={account.id} value={account.id}>
                    <Box display="flex" alignItems="center" gap={1}>
                      <Avatar src={account.profile_picture_url} sx={{ width: 24, height: 24 }} />
                      @{account.username}
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
          
          {/* Search */}
          <TextField
            fullWidth
            size="small"
            placeholder="Buscar conversas..."
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
        </Box>

        {/* Conversations List */}
        <List sx={{ flex: 1, overflow: 'auto', py: 0 }}>
          {loading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <CircularProgress />
            </Box>
          ) : filteredConversations.length === 0 ? (
            <Box textAlign="center" py={4} px={2}>
              <InstagramIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
              <Typography color="text.secondary">
                {searchQuery ? 'Nenhuma conversa encontrada' : 'Nenhuma conversa ainda'}
              </Typography>
            </Box>
          ) : (
            filteredConversations.map((conv) => (
              <React.Fragment key={conv.id}>
                <ListItemButton
                  selected={selectedConversation?.id === conv.id}
                  onClick={() => setSelectedConversation(conv)}
                  sx={{ py: 1.5 }}
                >
                  <ListItemAvatar>
                    <Badge
                      badgeContent={conv.unread_count}
                      color="error"
                      overlap="circular"
                    >
                      <Avatar src={conv.participant_profile_pic}>
                        {conv.participant_username?.[0]?.toUpperCase() || 'U'}
                      </Avatar>
                    </Badge>
                  </ListItemAvatar>
                  <ListItemText
                    primary={
                      <Box display="flex" justifyContent="space-between" alignItems="center">
                        <Typography
                          variant="body2"
                          fontWeight={conv.unread_count > 0 ? 'bold' : 'normal'}
                          noWrap
                        >
                          @{conv.participant_username || conv.participant_id}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {formatTime(conv.last_message_at)}
                        </Typography>
                      </Box>
                    }
                    secondary={
                      <Typography
                        variant="caption"
                        color={conv.unread_count > 0 ? 'text.primary' : 'text.secondary'}
                        fontWeight={conv.unread_count > 0 ? 500 : 400}
                        noWrap
                      >
                        {conv.last_message_preview || 'Nenhuma mensagem'}
                      </Typography>
                    }
                  />
                </ListItemButton>
                <Divider component="li" />
              </React.Fragment>
            ))
          )}
        </List>
      </Card>

      {/* Main - Chat Area */}
      <Card sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {!selectedConversation ? (
          <Box
            display="flex"
            flexDirection="column"
            alignItems="center"
            justifyContent="center"
            flex={1}
            color="text.secondary"
          >
            <InstagramIcon sx={{ fontSize: 80, color: '#E4405F', opacity: 0.5, mb: 2 }} />
            <Typography variant="h6">Selecione uma conversa</Typography>
            <Typography variant="body2">
              Escolha uma conversa da lista para ver as mensagens
            </Typography>
          </Box>
        ) : (
          <>
            {/* Chat Header */}
            <Box
              sx={{
                p: 2,
                borderBottom: 1,
                borderColor: 'divider',
                display: 'flex',
                alignItems: 'center',
                gap: 2,
              }}
            >
              <Avatar
                src={selectedConversation.participant_profile_pic}
                sx={{ width: 48, height: 48 }}
              >
                {selectedConversation.participant_username?.[0]?.toUpperCase()}
              </Avatar>
              <Box flex={1}>
                <Typography variant="subtitle1" fontWeight="bold">
                  {selectedConversation.participant_name || `@${selectedConversation.participant_username}`}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  @{selectedConversation.participant_username || selectedConversation.participant_id}
                </Typography>
              </Box>
              <Chip
                label={selectedConversation.status === 'active' ? 'Ativo' : 'Fechado'}
                color={selectedConversation.status === 'active' ? 'success' : 'default'}
                size="small"
              />
            </Box>

            {/* Messages Area */}
            <Box
              sx={{
                flex: 1,
                overflow: 'auto',
                p: 2,
                display: 'flex',
                flexDirection: 'column',
                gap: 1,
                bgcolor: 'grey.50',
              }}
            >
              {loadingMessages ? (
                <Box display="flex" justifyContent="center" py={4}>
                  <CircularProgress />
                </Box>
              ) : messages.length === 0 ? (
                <Box textAlign="center" py={4}>
                  <Typography color="text.secondary">
                    Nenhuma mensagem ainda. Envie a primeira!
                  </Typography>
                </Box>
              ) : (
                messages.map((msg) => (
                  <Box
                    key={msg.id}
                    sx={{
                      display: 'flex',
                      justifyContent: msg.direction === 'outbound' ? 'flex-end' : 'flex-start',
                    }}
                  >
                    <Paper
                      sx={{
                        p: 1.5,
                        maxWidth: '70%',
                        bgcolor: msg.direction === 'outbound' ? 'primary.main' : 'white',
                        color: msg.direction === 'outbound' ? 'white' : 'text.primary',
                        borderRadius: 2,
                        borderTopRightRadius: msg.direction === 'outbound' ? 0 : 2,
                        borderTopLeftRadius: msg.direction === 'inbound' ? 0 : 2,
                      }}
                    >
                      {msg.media_url && (
                        <Box mb={1}>
                          {msg.message_type === 'image' ? (
                            <img
                              src={msg.media_url}
                              alt="Imagem"
                              style={{ maxWidth: '100%', borderRadius: 8 }}
                            />
                          ) : msg.message_type === 'video' ? (
                            <video
                              src={msg.media_url}
                              controls
                              style={{ maxWidth: '100%', borderRadius: 8 }}
                            />
                          ) : (
                            <Chip icon={<ImageIcon />} label={msg.message_type} size="small" />
                          )}
                        </Box>
                      )}
                      {msg.text_content && (
                        <Typography variant="body2">{msg.text_content}</Typography>
                      )}
                      <Box
                        display="flex"
                        justifyContent="flex-end"
                        alignItems="center"
                        gap={0.5}
                        mt={0.5}
                      >
                        <Typography
                          variant="caption"
                          sx={{
                            opacity: 0.7,
                            fontSize: '0.65rem',
                          }}
                        >
                          {formatTime(msg.created_at)}
                        </Typography>
                        {msg.direction === 'outbound' && (
                          <Box sx={{ fontSize: '0.8rem', display: 'flex' }}>
                            {getStatusIcon(msg.status)}
                          </Box>
                        )}
                      </Box>
                    </Paper>
                  </Box>
                ))
              )}
              <div ref={messagesEndRef} />
            </Box>

            {/* Message Input */}
            <Box
              sx={{
                p: 2,
                borderTop: 1,
                borderColor: 'divider',
                display: 'flex',
                gap: 1,
              }}
            >
              <TextField
                fullWidth
                placeholder="Digite uma mensagem..."
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                multiline
                maxRows={4}
                disabled={sending}
              />
              <IconButton
                color="primary"
                onClick={handleSendMessage}
                disabled={!newMessage.trim() || sending}
                sx={{
                  bgcolor: 'primary.main',
                  color: 'white',
                  '&:hover': { bgcolor: 'primary.dark' },
                  '&:disabled': { bgcolor: 'grey.300' },
                }}
              >
                {sending ? <CircularProgress size={24} color="inherit" /> : <SendIcon />}
              </IconButton>
            </Box>
          </>
        )}
      </Card>

      {error && (
        <Alert
          severity="error"
          sx={{ position: 'fixed', bottom: 16, right: 16 }}
          onClose={() => setError(null)}
        >
          {error}
        </Alert>
      )}
    </Box>
  );
}
