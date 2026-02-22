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
  Tooltip,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import MessengerIcon from '@mui/icons-material/Chat'; // Using Chat as Messenger icon
import SendIcon from '@mui/icons-material/Send';
import SearchIcon from '@mui/icons-material/Search';
import RefreshIcon from '@mui/icons-material/Refresh';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import PersonIcon from '@mui/icons-material/Person';
import {
  messengerService,
  MessengerAccount,
  MessengerConversation,
  MessengerMessage,
} from '../../services/messenger';

export default function MessengerInbox() {
  const [accounts, setAccounts] = useState<MessengerAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [conversations, setConversations] = useState<MessengerConversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<MessengerConversation | null>(null);
  const [messages, setMessages] = useState<MessengerMessage[]>([]);
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
      const response = await messengerService.getAccounts();
      const results = response.data || [];
      setAccounts(results);
      if (results.length > 0) {
        setSelectedAccountId(results[0].id);
      }
    } catch (err) {
      console.error('Error loading accounts:', err);
      setError('Erro ao carregar contas do Messenger');
    } finally {
      setLoading(false);
    }
  };

  const loadConversations = async () => {
    if (!selectedAccountId) return;
    
    try {
      setLoading(true);
      const response = await messengerService.getConversations(selectedAccountId);
      setConversations(response.data || []);
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
      const response = await messengerService.getMessages(selectedConversation.id);
      setMessages(response.data || []);
      
      // Mark as read
      try {
        await messengerService.markAsRead(selectedConversation.id);
      } catch {
        // Silently ignore
      }
    } catch (err) {
      console.error('Error loading messages:', err);
    } finally {
      setLoadingMessages(false);
    }
  };

  const handleSendMessage = async () => {
    if (!newMessage.trim() || !selectedConversation) return;

    try {
      setSending(true);
      const response = await messengerService.sendMessage(selectedConversation.id, {
        content: newMessage.trim(),
        message_type: 'text',
      });
      
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

  const handleHandover = async (target: 'bot' | 'human') => {
    if (!selectedConversation) return;
    
    // TODO: Implement handover API call when backend supports it
    console.log(`Transferring conversation ${selectedConversation.id} to ${target}`);
  };

  const filteredConversations = conversations.filter((conv) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      conv.sender_name?.toLowerCase().includes(query) ||
      conv.last_message?.toLowerCase().includes(query)
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

  const getHandoverIcon = (status: string) => {
    switch (status) {
      case 'bot':
        return <SmartToyIcon fontSize="small" color="primary" />;
      case 'human':
        return <PersonIcon fontSize="small" color="success" />;
      default:
        return <SmartToyIcon fontSize="small" color="disabled" />;
    }
  };

  return (
    <Box sx={{ display: 'flex', height: 'calc(100vh - 100px)', gap: 2, p: 2 }}>
      {/* Sidebar - Conversations List */}
      <Card sx={{ width: 360, display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <Box display="flex" alignItems="center" gap={2} mb={2}>
            <MessengerIcon sx={{ color: '#0084FF', fontSize: 28 }} />
            <Typography variant="h6" fontWeight="bold">
              Messenger
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
              <InputLabel>Página</InputLabel>
              <Select
                value={selectedAccountId}
                label="Página"
                onChange={(e) => setSelectedAccountId(e.target.value)}
              >
                {accounts.map((account) => (
                  <MenuItem key={account.id} value={account.id}>
                    {account.page_name}
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
              <MessengerIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
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
                      <Avatar>
                        {conv.sender_name?.[0]?.toUpperCase() || 'U'}
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
                          {conv.sender_name || 'Usuário'}
                        </Typography>
                        <Box display="flex" alignItems="center" gap={0.5}>
                          {getHandoverIcon(conv.handover_status)}
                          <Typography variant="caption" color="text.secondary">
                            {formatTime(conv.last_message_at)}
                          </Typography>
                        </Box>
                      </Box>
                    }
                    secondary={
                      <Typography
                        variant="caption"
                        color={conv.unread_count > 0 ? 'text.primary' : 'text.secondary'}
                        fontWeight={conv.unread_count > 0 ? 500 : 400}
                        noWrap
                      >
                        {conv.last_message || 'Nenhuma mensagem'}
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
            <MessengerIcon sx={{ fontSize: 80, color: '#0084FF', opacity: 0.5, mb: 2 }} />
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
              <Avatar sx={{ width: 48, height: 48 }}>
                {selectedConversation.sender_name?.[0]?.toUpperCase()}
              </Avatar>
              <Box flex={1}>
                <Typography variant="subtitle1" fontWeight="bold">
                  {selectedConversation.sender_name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {selectedConversation.handover_status === 'bot' ? 'Modo Bot' : 'Atendimento Humano'}
                </Typography>
              </Box>
              
              {/* Handover Controls */}
              <Box display="flex" gap={1}>
                <Chip
                  icon={<SmartToyIcon />}
                  label="Bot"
                  color={selectedConversation.handover_status === 'bot' ? 'primary' : 'default'}
                  size="small"
                  onClick={() => handleHandover('bot')}
                  sx={{ cursor: 'pointer' }}
                />
                <Chip
                  icon={<PersonIcon />}
                  label="Humano"
                  color={selectedConversation.handover_status === 'human' ? 'success' : 'default'}
                  size="small"
                  onClick={() => handleHandover('human')}
                  sx={{ cursor: 'pointer' }}
                />
              </Box>
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
                      justifyContent: msg.is_from_bot ? 'flex-end' : 'flex-start',
                    }}
                  >
                    <Paper
                      sx={{
                        p: 1.5,
                        maxWidth: '70%',
                        bgcolor: msg.is_from_bot ? 'primary.main' : 'white',
                        color: msg.is_from_bot ? 'white' : 'text.primary',
                        borderRadius: 2,
                        borderTopRightRadius: msg.is_from_bot ? 0 : 2,
                        borderTopLeftRadius: msg.is_from_bot ? 2 : 0,
                      }}
                    >
                      {msg.attachments && msg.attachments.length > 0 && (
                        <Box mb={1}>
                          {msg.attachments.map((att, idx) => (
                            <Box key={idx}>
                              {att.type === 'image' ? (
                                <img
                                  src={att.url}
                                  alt="Attachment"
                                  style={{ maxWidth: '100%', borderRadius: 8 }}
                                />
                              ) : (
                                <Chip label={att.name || att.type} size="small" />
                              )}
                            </Box>
                          ))}
                        </Box>
                      )}
                      {msg.content && (
                        <Typography variant="body2">{msg.content}</Typography>
                      )}
                      <Typography
                        variant="caption"
                        sx={{
                          opacity: 0.7,
                          fontSize: '0.65rem',
                          display: 'block',
                          textAlign: 'right',
                          mt: 0.5,
                        }}
                      >
                        {formatTime(msg.created_at)}
                      </Typography>
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
