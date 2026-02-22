import React, { useState, useRef, useEffect, useCallback } from 'react';
import { 
  PaperAirplaneIcon,
  TrashIcon,
  UserCircleIcon,
  CpuChipIcon,
  ClockIcon,
  ServerIcon,
  DocumentTextIcon,
  VariableIcon,
  PlayIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ChatBubbleLeftRightIcon,
  BoltIcon,
  SparklesIcon,
  ChatBubbleBottomCenterTextIcon,
  ShoppingCartIcon,
  ShoppingBagIcon,
  CreditCardIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';
import { cn } from '../../utils/cn';
import agentsService from '../../services/agents';
import { useAccountStore } from '../../stores/accountStore';

// Types
interface TestMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  source?: 'jasper' | 'template' | 'handler' | 'agent' | 'fallback';
  buttons?: Array<{ id: string; title: string }>;
  metadata?: {
    intent?: string;
    jasper_template?: string;
    template_event?: string;
    model?: string;
    processing_time_ms?: number;
  };
}

interface FlowStep {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
  messages: string[];
}

const FLOW_STEPS: FlowStep[] = [
  {
    id: 'greeting',
    title: 'Saudação',
    description: 'Teste a mensagem inicial com Jasper greeting',
    icon: SparklesIcon,
    messages: ['Oi', 'Olá', 'Bom dia'],
  },
  {
    id: 'menu',
    title: 'Cardápio',
    description: 'Teste a exibição do menu com categorias',
    icon: DocumentTextIcon,
    messages: ['Cardápio', 'Ver menu', 'O que vocês têm?'],
  },
  {
    id: 'product',
    title: 'Produto',
    description: 'Teste a exibição de um produto',
    icon: ShoppingBagIcon,
    messages: ['Quero ver produtos', 'Mostre o cardápio'],
  },
  {
    id: 'cart',
    title: 'Carrinho',
    description: 'Teste o resumo do carrinho',
    icon: ShoppingCartIcon,
    messages: ['Ver carrinho', 'Meu carrinho', 'O que tenho no carrinho?'],
  },
  {
    id: 'order',
    title: 'Pedido',
    description: 'Teste status do pedido',
    icon: CreditCardIcon,
    messages: ['Status do pedido', 'Onde está meu pedido?'],
  },
  {
    id: 'help',
    title: 'Ajuda',
    description: 'Teste mensagem de ajuda',
    icon: QuestionMarkCircleIcon,
    messages: ['Ajuda', 'Não entendi', 'Preciso de ajuda'],
  },
];

export const UnifiedOrchestratorTest: React.FC = () => {
  const { accounts } = useAccountStore();
  const account = accounts[0];
  
  const [messages, setMessages] = useState<TestMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState('5511999999999');
  const [showContext, setShowContext] = useState(false);
  const [lastContext, setLastContext] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    
    if (!inputValue.trim() || isLoading || !account) return;

    const userMessage: TestMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const response = await agentsService.processUnified(account.id, {
        message: userMessage.content,
        phone_number: phoneNumber,
        use_llm: true,
        enable_templates: true,
        enable_handlers: true,
      });

      const assistantMessage: TestMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.content,
        timestamp: new Date(),
        source: response.source as any,
        buttons: response.buttons,
        metadata: response.metadata as any,
      };

      setMessages(prev => [...prev, assistantMessage]);
      
      // Store context for debugging
      if (response.metadata?.context) {
        setLastContext(JSON.stringify(response.metadata.context, null, 2));
      }
    } catch (error) {
      console.error('Error:', error);
      const errorMessage: TestMessage = {
        id: `error-${Date.now()}`,
        role: 'system',
        content: 'Erro ao processar mensagem. Verifique se o orquestrador está configurado.',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleClear = () => {
    setMessages([]);
    setLastContext('');
  };

  const handleQuickTest = (message: string) => {
    setInputValue(message);
    setTimeout(() => handleSubmit(), 100);
  };

  const getSourceIcon = (source?: string) => {
    switch (source) {
      case 'jasper':
        return <SparklesIcon className="w-4 h-4 text-purple-500" />;
      case 'template':
        return <DocumentTextIcon className="w-4 h-4 text-blue-500" />;
      case 'handler':
        return <BoltIcon className="w-4 h-4 text-yellow-500" />;
      case 'agent':
        return <CpuChipIcon className="w-4 h-4 text-green-500" />;
      default:
        return <ServerIcon className="w-4 h-4 text-gray-500" />;
    }
  };

  const getSourceLabel = (source?: string) => {
    switch (source) {
      case 'jasper':
        return 'Jasper Template';
      case 'template':
        return 'AutoMessage';
      case 'handler':
        return 'Handler';
      case 'agent':
        return 'LLM Direto';
      default:
        return 'Fallback';
    }
  };

  const getSourceColor = (source?: string) => {
    switch (source) {
      case 'jasper':
        return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300';
      case 'template':
        return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300';
      case 'handler':
        return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300';
      case 'agent':
        return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300';
      default:
        return 'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-300';
    }
  };

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-[700px] bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 bg-gradient-to-r from-primary-600 to-primary-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
              <CpuChipIcon className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-semibold text-white text-lg">
                Teste do Orquestrador Unificado
              </h1>
              <p className="text-primary-100 text-sm">
                LLM + Templates + Handlers + Jasper
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowContext(!showContext)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                showContext 
                  ? "bg-white text-primary-600" 
                  : "bg-white/20 text-white hover:bg-white/30"
              )}
            >
              <VariableIcon className="w-4 h-4 inline mr-1" />
              Contexto
            </button>
            <button
              onClick={handleClear}
              className="p-2 rounded-lg text-white/80 hover:text-white hover:bg-white/20 transition-colors"
            >
              <TrashIcon className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Phone Input */}
        <div className="px-4 py-2 bg-zinc-50 dark:bg-zinc-800/50 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
          <span className="text-sm text-zinc-500 dark:text-zinc-400">Telefone:</span>
          <input
            type="text"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            className="flex-1 px-3 py-1 text-sm bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg"
            placeholder="5511999999999"
          />
          {account && (
            <span className="text-xs text-zinc-400">
              Conta: {account.name}
            </span>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-20 h-20 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center mb-4">
                <ChatBubbleLeftRightIcon className="w-10 h-10 text-primary-600 dark:text-primary-400" />
              </div>
              <h3 className="text-xl font-medium text-zinc-900 dark:text-white mb-2">
                Teste o Orquestrador Unificado
              </h3>
              <p className="text-zinc-500 dark:text-zinc-400 max-w-md mb-6">
                Envie uma mensagem para ver o LLM em ação com templates Jasper, 
                AutoMessages, Handlers e respostas diretas.
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {['Oi', 'Cardápio', 'Ver carrinho', 'Status do pedido'].map((msg) => (
                  <button
                    key={msg}
                    onClick={() => handleQuickTest(msg)}
                    className="px-4 py-2 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded-full text-sm text-zinc-700 dark:text-zinc-300 transition-colors"
                  >
                    {msg}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  "flex gap-3",
                  message.role === 'user' ? "justify-end" : "justify-start"
                )}
              >
                {message.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center flex-shrink-0">
                    <CpuChipIcon className="w-4 h-4 text-primary-600 dark:text-primary-400" />
                  </div>
                )}
                
                <div className={cn(
                  "max-w-[85%] rounded-2xl px-4 py-3",
                  message.role === 'user'
                    ? "bg-primary-600 text-white rounded-br-md"
                    : "bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-white rounded-bl-md"
                )}>
                  {/* Source Badge */}
                  {message.role === 'assistant' && message.source && (
                    <div className="flex items-center gap-2 mb-2">
                      <span className={cn(
                        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
                        getSourceColor(message.source)
                      )}>
                        {getSourceIcon(message.source)}
                        {getSourceLabel(message.source)}
                      </span>
                      {message.metadata?.jasper_template && (
                        <span className="text-xs text-zinc-500">
                          {message.metadata.jasper_template}
                        </span>
                      )}
                      {message.metadata?.template_event && (
                        <span className="text-xs text-zinc-500">
                          {message.metadata.template_event}
                        </span>
                      )}
                    </div>
                  )}
                  
                  {/* Content */}
                  <p className="whitespace-pre-wrap break-words">{message.content}</p>
                  
                  {/* Buttons */}
                  {message.buttons && message.buttons.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {message.buttons.map((btn) => (
                        <button
                          key={btn.id}
                          onClick={() => handleQuickTest(btn.title)}
                          className="px-3 py-1.5 bg-white dark:bg-zinc-700 border border-zinc-200 dark:border-zinc-600 rounded-lg text-sm text-zinc-700 dark:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-600 transition-colors"
                        >
                          {btn.title}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Metadata */}
                  {message.metadata && (
                    <div className="flex items-center gap-3 mt-2 pt-2 border-t border-zinc-200 dark:border-zinc-700">
                      {message.metadata.model && (
                        <span className="text-xs text-zinc-500">
                          {message.metadata.model}
                        </span>
                      )}
                      {message.metadata.processing_time_ms && (
                        <span className="flex items-center gap-1 text-xs text-zinc-500">
                          <ClockIcon className="w-3 h-3" />
                          {message.metadata.processing_time_ms}ms
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {message.role === 'user' && (
                  <div className="w-8 h-8 rounded-full bg-zinc-200 dark:bg-zinc-700 flex items-center justify-center flex-shrink-0">
                    <UserCircleIcon className="w-4 h-4 text-zinc-600 dark:text-zinc-400" />
                  </div>
                )}
              </div>
            ))
          )}
          
          {/* Loading indicator */}
          {isLoading && (
            <div className="flex gap-3 justify-start">
              <div className="w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center flex-shrink-0">
                <CpuChipIcon className="w-4 h-4 text-primary-600 dark:text-primary-400" />
              </div>
              <div className="bg-zinc-100 dark:bg-zinc-800 rounded-2xl rounded-bl-md px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-zinc-400 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-zinc-400 rounded-full animate-bounce delay-100" />
                  <div className="w-2 h-2 bg-zinc-400 rounded-full animate-bounce delay-200" />
                  <span className="text-sm text-zinc-500 dark:text-zinc-400 ml-2">
                    Orquestrador processando...
                  </span>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="p-4 border-t border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/50">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Digite sua mensagem para testar o orquestrador..."
              disabled={isLoading}
              rows={1}
              className={cn(
                "flex-1 px-4 py-3 rounded-xl border resize-none",
                "bg-white dark:bg-zinc-800",
                "text-zinc-900 dark:text-white placeholder-zinc-400",
                "border-zinc-200 dark:border-zinc-700",
                "focus:ring-2 focus:ring-primary-500 focus:border-transparent",
                "disabled:opacity-50"
              )}
            />
            <button
              type="submit"
              disabled={isLoading || !inputValue.trim()}
              className={cn(
                "px-4 py-3 rounded-xl transition-colors flex items-center gap-2",
                "bg-primary-600 hover:bg-primary-700 text-white",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              <PaperAirplaneIcon className="w-5 h-5" />
              Enviar
            </button>
          </form>
          <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-2 text-center">
            Pressione Enter para enviar • Shift+Enter para nova linha
          </p>
        </div>
      </div>

      {/* Sidebar */}
      <div className="w-full lg:w-80 space-y-4">
        {/* Flow Steps */}
        <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
          <h3 className="font-medium text-zinc-900 dark:text-white mb-4 flex items-center gap-2">
            <PlayIcon className="w-5 h-5 text-primary-500" />
            Fluxos de Teste
          </h3>
          <div className="space-y-2">
            {FLOW_STEPS.map((step) => (
              <div
                key={step.id}
                className="p-3 rounded-lg bg-zinc-50 dark:bg-zinc-800/50 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
              >
                <div className="flex items-center gap-2 mb-1">
                  <step.icon className="w-4 h-4 text-zinc-500" />
                  <span className="font-medium text-sm text-zinc-900 dark:text-white">
                    {step.title}
                  </span>
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">
                  {step.description}
                </p>
                <div className="flex flex-wrap gap-1">
                  {step.messages.map((msg) => (
                    <button
                      key={msg}
                      onClick={() => handleQuickTest(msg)}
                      className="px-2 py-1 bg-white dark:bg-zinc-700 border border-zinc-200 dark:border-zinc-600 rounded text-xs text-zinc-600 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-600 transition-colors"
                    >
                      {msg}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* How it Works */}
        <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
          <h3 className="font-medium text-zinc-900 dark:text-white mb-4 flex items-center gap-2">
            <ServerIcon className="w-5 h-5 text-primary-500" />
            Como Funciona
          </h3>
          <div className="space-y-3 text-sm">
            <div className="flex items-start gap-2">
              <CheckCircleIcon className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
              <span className="text-zinc-600 dark:text-zinc-400">
                <strong>1. Detecta Intent:</strong> Analisa a mensagem do cliente
              </span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircleIcon className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
              <span className="text-zinc-600 dark:text-zinc-400">
                <strong>2. Coleta Contexto:</strong> Busca templates, store, produtos
              </span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircleIcon className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
              <span className="text-zinc-600 dark:text-zinc-400">
                <strong>3. LLM Decide:</strong> Escolhe a melhor resposta
              </span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircleIcon className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
              <span className="text-zinc-600 dark:text-zinc-400">
                <strong>4. Renderiza:</strong> Aplica variáveis reais da Store
              </span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircleIcon className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
              <span className="text-zinc-600 dark:text-zinc-400">
                <strong>5. Responde:</strong> Envia com botões interativos
              </span>
            </div>
          </div>
        </div>

        {/* Sources Info */}
        <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
          <h3 className="font-medium text-zinc-900 dark:text-white mb-4">
            Fontes de Resposta
          </h3>
          <div className="space-y-2">
            <div className="flex items-center gap-2 p-2 rounded-lg bg-purple-50 dark:bg-purple-900/20">
              <SparklesIcon className="w-4 h-4 text-purple-500" />
              <div>
                <span className="text-sm font-medium text-zinc-900 dark:text-white">Jasper Template</span>
                <p className="text-xs text-zinc-500">Templates profissionais com botões</p>
              </div>
            </div>
            <div className="flex items-center gap-2 p-2 rounded-lg bg-blue-50 dark:bg-blue-900/20">
              <DocumentTextIcon className="w-4 h-4 text-blue-500" />
              <div>
                <span className="text-sm font-medium text-zinc-900 dark:text-white">AutoMessage</span>
                <p className="text-xs text-zinc-500">Templates configuráveis do banco</p>
              </div>
            </div>
            <div className="flex items-center gap-2 p-2 rounded-lg bg-yellow-50 dark:bg-yellow-900/20">
              <BoltIcon className="w-4 h-4 text-yellow-500" />
              <div>
                <span className="text-sm font-medium text-zinc-900 dark:text-white">Handler</span>
                <p className="text-xs text-zinc-500">Lógica específica por intent</p>
              </div>
            </div>
            <div className="flex items-center gap-2 p-2 rounded-lg bg-green-50 dark:bg-green-900/20">
              <CpuChipIcon className="w-4 h-4 text-green-500" />
              <div>
                <span className="text-sm font-medium text-zinc-900 dark:text-white">LLM Direto</span>
                <p className="text-xs text-zinc-500">Resposta gerada pelo modelo</p>
              </div>
            </div>
          </div>
        </div>

        {/* Context Debug */}
        {showContext && lastContext && (
          <div className="bg-slate-900 rounded-xl border border-slate-700 p-4">
            <h3 className="font-medium text-slate-200 mb-2 flex items-center gap-2">
              <VariableIcon className="w-4 h-4" />
              Contexto do LLM
            </h3>
            <pre className="text-xs text-slate-400 overflow-auto max-h-60">
              {lastContext}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};

export default UnifiedOrchestratorTest;
