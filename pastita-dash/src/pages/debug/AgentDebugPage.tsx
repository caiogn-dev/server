import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress,
  Chip,
  Divider,
} from '@mui/material';
import api from '@/services/api';

interface DebugResult {
  timestamp: string;
  conversation?: {
    id: string;
    status: string;
  };
  account?: {
    id: string;
    phone_number: string;
    has_default_agent: boolean;
  };
  agent?: {
    id: string;
    name: string;
    is_active: boolean;
    model: string;
  };
  handover?: {
    id: string;
    status: string;
    assigned_to: string | null;
  } | null;
  checks: {
    agent_active?: boolean;
    handover_bot_mode?: boolean;
    agent_error?: string;
  };
  agent_would_respond: boolean;
  recommendation: string;
}

export default function AgentDebugPage() {
  const [conversationId, setConversationId] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DebugResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkStatus = async () => {
    if (!conversationId.trim()) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await api.get(`/debug/agent-status/?conversation_id=${conversationId}`);
      setResult(response.data);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Erro ao verificar status');
    } finally {
      setLoading(false);
    }
  };

  const forceHandover = async (target: 'bot' | 'human') => {
    if (!conversationId.trim()) return;
    
    try {
      setLoading(true);
      await api.post(`/conversations/${conversationId}/force-handover/`, {
        target,
        reason: 'Manual override from debug page'
      });
      await checkStatus();
    } catch (err: any) {
      setError(err.response?.data?.error || 'Erro ao transferir');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box p={3}>
      <Typography variant="h4" fontWeight="bold" mb={3}>
        Diagnóstico do Agente AI
      </Typography>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Verificar Status
          </Typography>
          
          <Box display="flex" gap={2} mb={2}>
            <TextField
              fullWidth
              label="ID da Conversa"
              value={conversationId}
              onChange={(e) => setConversationId(e.target.value)}
              placeholder="cb85ebf4-2d3d-443a-a117-18c2b7122083"
            />
            <Button
              variant="contained"
              onClick={checkStatus}
              disabled={loading || !conversationId.trim()}
            >
              {loading ? <CircularProgress size={24} /> : 'Verificar'}
            </Button>
          </Box>

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Resultado do Diagnóstico
            </Typography>

            {/* Status Geral */}
            <Box mb={3}>
              <Chip
                label={result.agent_would_respond ? 'AGENTE ESTÁ RESPONDENDO' : 'AGENTE NÃO RESPONDE'}
                color={result.agent_would_respond ? 'error' : 'success'}
                sx={{ fontSize: '1rem', py: 1 }}
              />
              <Typography variant="body2" color="text.secondary" mt={1}>
                {result.recommendation}
              </Typography>
            </Box>

            <Divider sx={{ my: 2 }} />

            {/* Checks */}
            <Typography variant="subtitle2" gutterBottom>
              Verificações:
            </Typography>
            <Box display="flex" gap={1} mb={2}>
              <Chip
                size="small"
                label={result.checks.agent_active ? 'Agente Ativo' : 'Agente Inativo'}
                color={result.checks.agent_active ? 'success' : 'error'}
              />
              <Chip
                size="small"
                label={result.checks.handover_bot_mode ? 'Modo Bot' : 'Modo Humano'}
                color={result.checks.handover_bot_mode ? 'success' : 'warning'}
              />
            </Box>

            {/* Agent Info */}
            {result.agent && (
              <>
                <Typography variant="subtitle2" gutterBottom>
                  Agente:
                </Typography>
                <Box mb={2}>
                  <Typography variant="body2">
                    <strong>Nome:</strong> {result.agent.name}
                  </Typography>
                  <Typography variant="body2">
                    <strong>Status:</strong> {result.agent.is_active ? 'Ativo' : 'Inativo'}
                  </Typography>
                  <Typography variant="body2">
                    <strong>Modelo:</strong> {result.agent.model}
                  </Typography>
                </Box>
              </>
            )}

            {/* Handover Info */}
            <Typography variant="subtitle2" gutterBottom>
              Handover:
            </Typography>
            {result.handover ? (
              <Box mb={2}>
                <Typography variant="body2">
                  <strong>Status:</strong> {result.handover.status}
                </Typography>
                <Typography variant="body2">
                  <strong>Atribuído a:</strong> {result.handover.assigned_to || 'Ninguém'}
                </Typography>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Sem registro de handover (assume modo bot)
              </Typography>
            )}

            <Divider sx={{ my: 2 }} />

            {/* Ações */}
            <Typography variant="subtitle2" gutterBottom>
              Ações:
            </Typography>
            <Box display="flex" gap={2}>
              <Button
                variant="outlined"
                color="primary"
                onClick={() => forceHandover('bot')}
                disabled={loading}
              >
                Forçar Modo Bot
              </Button>
              <Button
                variant="outlined"
                color="secondary"
                onClick={() => forceHandover('human')}
                disabled={loading}
              >
                Forçar Modo Humano
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
