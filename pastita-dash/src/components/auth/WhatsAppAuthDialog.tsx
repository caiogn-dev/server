/**
 * WhatsApp Authentication Component
 * 
 * Fluxo de autenticação via WhatsApp:
 * 1. Usuário digita número de telefone
 * 2. Sistema envia código via WhatsApp (template de autenticação)
 * 3. Usuário recebe código e digita
 * 4. Sistema valida e autentica
 */
import React, { useState, useRef, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Loader2,
  MessageCircle,
  CheckCircle2,
  AlertCircle,
  ArrowLeft,
  RefreshCw,
  Smartphone,
  Lock,
} from 'lucide-react';
import api from '@/services/api';
import { useToast } from '@/hooks/useToast';

interface WhatsAppAuthDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (user: any) => void;
  whatsappAccountId: string;
}

type Step = 'phone' | 'code' | 'success';

export const WhatsAppAuthDialog: React.FC<WhatsAppAuthDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  whatsappAccountId,
}) => {
  const toast = useToast();
  const [step, setStep] = useState<Step>('phone');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState(['', '', '', '', '', '']);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [remainingAttempts, setRemainingAttempts] = useState(3);
  
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Countdown para reenvio
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(c => c - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  // Reset ao abrir
  useEffect(() => {
    if (isOpen) {
      setStep('phone');
      setPhone('');
      setCode(['', '', '', '', '', '']);
      setError('');
      setCountdown(0);
      setRemainingAttempts(3);
    }
  }, [isOpen]);

  // Focar primeiro input ao entrar na tela de código
  useEffect(() => {
    if (step === 'code') {
      setTimeout(() => inputRefs.current[0]?.focus(), 100);
    }
  }, [step]);

  const formatPhone = (value: string) => {
    const numbers = value.replace(/\D/g, '');
    if (numbers.length <= 2) return numbers;
    if (numbers.length <= 7) return `(${numbers.slice(0, 2)}) ${numbers.slice(2)}`;
    return `(${numbers.slice(0, 2)}) ${numbers.slice(2, 7)}-${numbers.slice(7, 11)}`;
  };

  const handleSendCode = async () => {
    setError('');
    setIsLoading(true);
    
    try {
      const cleanPhone = phone.replace(/\D/g, '');
      const fullPhone = cleanPhone.startsWith('55') ? cleanPhone : `55${cleanPhone}`;
      
      const response = await api.post('/auth/whatsapp/send/', {
        phone_number: `+${fullPhone}`,
        whatsapp_account_id: whatsappAccountId,
      });
      
      if (response.data.success) {
        setStep('code');
        setCountdown(60); // 1 minuto para reenviar
        toast.success('Código enviado!', 'Verifique seu WhatsApp');
      } else {
        setError(response.data.message || 'Erro ao enviar código');
        if (response.data.retry_after) {
          setCountdown(response.data.retry_after);
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.message || 'Erro ao enviar código. Tente novamente.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResendCode = async () => {
    setError('');
    setIsLoading(true);
    
    try {
      const cleanPhone = phone.replace(/\D/g, '');
      const fullPhone = cleanPhone.startsWith('55') ? cleanPhone : `55${cleanPhone}`;
      
      const response = await api.post('/auth/whatsapp/resend/', {
        phone_number: `+${fullPhone}`,
        whatsapp_account_id: whatsappAccountId,
      });
      
      if (response.data.success) {
        setCountdown(60);
        setCode(['', '', '', '', '', '']);
        toast.success('Código reenviado!', 'Verifique seu WhatsApp');
      } else {
        setError(response.data.message || 'Erro ao reenviar código');
      }
    } catch (err: any) {
      setError(err.response?.data?.message || 'Erro ao reenviar código');
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyCode = async () => {
    const fullCode = code.join('');
    
    if (fullCode.length !== 6) {
      setError('Digite o código completo de 6 dígitos');
      return;
    }
    
    setError('');
    setIsLoading(true);
    
    try {
      const cleanPhone = phone.replace(/\D/g, '');
      const fullPhone = cleanPhone.startsWith('55') ? cleanPhone : `55${cleanPhone}`;
      
      const response = await api.post('/auth/whatsapp/verify/', {
        phone_number: `+${fullPhone}`,
        code: fullCode,
      });
      
      if (response.data.valid) {
        setStep('success');
        toast.success('Autenticação realizada!', 'Bem-vindo!');
        
        setTimeout(() => {
          onSuccess(response.data.user);
          onClose();
        }, 1500);
      } else {
        setError(response.data.message || 'Código inválido');
        if (response.data.remaining_attempts !== undefined) {
          setRemainingAttempts(response.data.remaining_attempts);
        }
        setCode(['', '', '', '', '', '']);
        inputRefs.current[0]?.focus();
      }
    } catch (err: any) {
      setError(err.response?.data?.message || 'Erro ao verificar código');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCodeChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return;
    
    const newCode = [...code];
    newCode[index] = value.slice(-1);
    setCode(newCode);
    
    // Auto-focus próximo input
    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
    
    // Auto-submit quando completo
    if (index === 5 && value) {
      const fullCode = [...newCode.slice(0, 5), value].join('');
      if (fullCode.length === 6) {
        setTimeout(() => handleVerifyCode(), 300);
      }
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageCircle className="w-6 h-6 text-green-500" />
            Login com WhatsApp
          </DialogTitle>
        </DialogHeader>

        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {step === 'phone' && (
          <div className="space-y-4">
            <div className="text-center py-4">
              <div className="w-20 h-20 mx-auto mb-4 bg-green-100 rounded-full flex items-center justify-center">
                <Smartphone className="w-10 h-10 text-green-600" />
              </div>
              <p className="text-gray-600">
                Digite seu número de WhatsApp para receber um código de verificação
              </p>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="phone">Número de WhatsApp</Label>
              <Input
                id="phone"
                type="tel"
                placeholder="(11) 99999-9999"
                value={phone}
                onChange={(e) => setPhone(formatPhone(e.target.value))}
                maxLength={15}
                className="text-lg text-center"
              />
            </div>
            
            <Button
              onClick={handleSendCode}
              disabled={isLoading || phone.replace(/\D/g, '').length < 10}
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Enviando...
                </>
              ) : (
                'Enviar Código'
              )}
            </Button>
            
            <p className="text-xs text-center text-gray-500">
              Você receberá um código de 6 dígitos no WhatsApp
            </p>
          </div>
        )}

        {step === 'code' && (
          <div className="space-y-4">
            <div className="text-center py-2">
              <div className="w-16 h-16 mx-auto mb-3 bg-green-100 rounded-full flex items-center justify-center">
                <Lock className="w-8 h-8 text-green-600" />
              </div>
              <p className="text-gray-600">
                Digite o código de 6 dígitos enviado para
              </p>
              <p className="font-semibold text-lg">{phone}</p>
            </div>
            
            <div className="flex justify-center gap-2">
              {code.map((digit, index) => (
                <Input
                  key={index}
                  ref={(el) => { inputRefs.current[index] = el; }}
                  type="text"
                  inputMode="numeric"
                  value={digit}
                  onChange={(e) => handleCodeChange(index, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(index, e)}
                  className="w-12 h-14 text-center text-2xl font-bold"
                  maxLength={1}
                />
              ))}
            </div>
            
            {remainingAttempts < 3 && (
              <p className="text-center text-sm text-amber-600">
                {remainingAttempts} tentativas restantes
              </p>
            )}
            
            <Button
              onClick={handleVerifyCode}
              disabled={isLoading || code.join('').length !== 6}
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verificando...
                </>
              ) : (
                'Verificar Código'
              )}
            </Button>
            
            <div className="flex items-center justify-between">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setStep('phone')}
                className="text-gray-500"
              >
                <ArrowLeft className="w-4 h-4 mr-1" />
                Voltar
              </Button>
              
              {countdown > 0 ? (
                <span className="text-sm text-gray-500">
                  Reenviar em {countdown}s
                </span>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleResendCode}
                  disabled={isLoading}
                >
                  <RefreshCw className="w-4 h-4 mr-1" />
                  Reenviar código
                </Button>
              )}
            </div>
          </div>
        )}

        {step === 'success' && (
          <div className="text-center py-8">
            <div className="w-20 h-20 mx-auto mb-4 bg-green-100 rounded-full flex items-center justify-center animate-bounce">
              <CheckCircle2 className="w-10 h-10 text-green-600" />
            </div>
            <h3 className="text-xl font-semibold mb-2">Autenticado!</h3>
            <p className="text-gray-600">Redirecionando...</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default WhatsAppAuthDialog;
