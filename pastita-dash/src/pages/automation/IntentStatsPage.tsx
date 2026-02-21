import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  ArrowPathIcon,
  ChartBarIcon,
  BoltIcon,
  CpuChipIcon,
  CheckCircleIcon,
  ShoppingCartIcon,
  CreditCardIcon,
  ChatBubbleLeftRightIcon,
} from '@heroicons/react/24/outline';
import { DateRange } from 'react-date-range';
import { ptBR } from 'date-fns/locale';
import { format, subDays } from 'date-fns';
import { toast } from 'react-hot-toast';
import { cn } from '../../utils/cn';
import { Loading } from '../../components/common/Loading';
import { intentService, intentTypeLabels } from '../../services';
import type { IntentStats, IntentType } from '../../types';
import 'react-date-range/dist/styles.css';
import 'react-date-range/dist/theme/default.css';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  className?: string;
}

const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  trend,
  trendValue,
  className,
}) => (
  <div className={cn('bg-white dark:bg-zinc-800 rounded-xl p-6 shadow-sm', className)}>
    <div className="flex items-start justify-between">
      <div>
        <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{title}</p>
        <h3 className="text-2xl font-bold text-zinc-900 dark:text-white mt-2">{value}</h3>
        {subtitle && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">{subtitle}</p>
        )}
        {trend && trendValue && (
          <div className={cn(
            'flex items-center gap-1 mt-2 text-sm',
            trend === 'up' && 'text-green-600 dark:text-green-400',
            trend === 'down' && 'text-red-600 dark:text-red-400',
            trend === 'neutral' && 'text-zinc-500 dark:text-zinc-400'
          )}>
            {trend === 'up' && '↑'}
            {trend === 'down' && '↓'}
            {trend === 'neutral' && '→'}
            <span>{trendValue}</span>
          </div>
        )}
      </div>
      <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
        {icon}
      </div>
    </div>
  </div>
);

export const IntentStatsPage: React.FC = () => {
  const { companyId } = useParams<{ companyId: string }>();
  const [stats, setStats] = useState<IntentStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState([
    {
      startDate: subDays(new Date(), 7),
      endDate: new Date(),
      key: 'selection',
    },
  ]);
  const [showDatePicker, setShowDatePicker] = useState(false);

  const loadStats = async () => {
    try {
      setLoading(true);
      const data = await intentService.getStats({
        start_date: format(dateRange[0].startDate, 'yyyy-MM-dd'),
        end_date: format(dateRange[0].endDate, 'yyyy-MM-dd'),
        company_id: companyId,
      });
      setStats(data);
    } catch (error) {
      toast.error('Erro ao carregar estatísticas');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, [dateRange, companyId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loading size="lg" />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="text-center py-12">
        <p className="text-zinc-500 dark:text-zinc-400">
          Nenhuma estatística disponível para o período selecionado.
        </p>
      </div>
    );
  }

  // Calcula porcentagens
  const regexPercentage = stats.total_detected > 0
    ? ((stats.by_method.regex / stats.total_detected) * 100).toFixed(1)
    : '0';
  const llmPercentage = stats.total_detected > 0
    ? ((stats.by_method.llm / stats.total_detected) * 100).toFixed(1)
    : '0';

  // Top intenções
  const topIntents = stats.top_intents || [];

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
            Estatísticas de Intenções
          </h1>
          <p className="text-zinc-500 dark:text-zinc-400 mt-1">
            Análise de detecção de intenções do sistema
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Date Range Picker */}
          <div className="relative">
            <button
              onClick={() => setShowDatePicker(!showDatePicker)}
              className={cn(
                'px-4 py-2 rounded-lg border text-sm font-medium',
                'border-zinc-300 dark:border-zinc-600',
                'bg-white dark:bg-zinc-800',
                'text-zinc-700 dark:text-zinc-300',
                'hover:bg-zinc-50 dark:hover:bg-zinc-700',
                'transition-colors'
              )}
            >
              {format(dateRange[0].startDate, 'dd/MM/yyyy')} - {format(dateRange[0].endDate, 'dd/MM/yyyy')}
            </button>
            {showDatePicker && (
              <div className="absolute right-0 top-full mt-2 z-50">
                <DateRange
                  ranges={dateRange}
                  onChange={(item: any) => {
                    setDateRange([item.selection]);
                    setShowDatePicker(false);
                  }}
                  locale={ptBR}
                  maxDate={new Date()}
                />
              </div>
            )}
          </div>
          <button
            onClick={loadStats}
            className="p-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
            title="Atualizar"
          >
            <ArrowPathIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="Total de Intenções"
          value={stats.total_detected.toLocaleString()}
          subtitle="Mensagens processadas"
          icon={<ChatBubbleLeftRightIcon className="w-6 h-6 text-blue-600" />}
        />
        <StatCard
          title="Detecção Regex"
          value={`${regexPercentage}%`}
          subtitle={`${stats.by_method.regex.toLocaleString()} mensagens`}
          icon={<BoltIcon className="w-6 h-6 text-green-600" />}
          trend="up"
          trendValue="Rápido e gratuito"
        />
        <StatCard
          title="Detecção LLM"
          value={`${llmPercentage}%`}
          subtitle={`${stats.by_method.llm.toLocaleString()} mensagens`}
          icon={<CpuChipIcon className="w-6 h-6 text-purple-600" />}
          trend={parseFloat(llmPercentage) > 30 ? 'down' : 'up'}
          trendValue="Fallback para casos complexos"
        />
        <StatCard
          title="Tempo Médio"
          value={`${(stats.avg_response_time_ms / 1000).toFixed(2)}s`}
          subtitle="Tempo de resposta"
          icon={<ChartBarIcon className="w-6 h-6 text-orange-600" />}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Intents by Type */}
        <div className="bg-white dark:bg-zinc-800 rounded-xl p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-white mb-4">
            Intenções por Tipo
          </h3>
          <div className="space-y-3">
            {Object.entries(stats.by_type)
              .sort(([,a], [,b]) => (b as number) - (a as number))
              .slice(0, 10)
              .map(([intent, count]) => {
                const percentage = stats.total_detected > 0
                  ? ((count as number) / stats.total_detected * 100).toFixed(1)
                  : '0';
                return (
                  <div key={intent} className="flex items-center gap-4">
                    <div className="w-32 text-sm text-zinc-600 dark:text-zinc-400 truncate">
                      {intentTypeLabels[intent] || intent}
                    </div>
                    <div className="flex-1">
                      <div className="h-2 bg-zinc-100 dark:bg-zinc-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                    <div className="w-20 text-right text-sm text-zinc-600 dark:text-zinc-400">
                      {count as number} ({percentage}%)
                    </div>
                  </div>
                );
              })}
          </div>
        </div>

        {/* Top Intents */}
        <div className="bg-white dark:bg-zinc-800 rounded-xl p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-white mb-4">
            Top Intenções
          </h3>
          {topIntents.length > 0 ? (
            <div className="space-y-4">
              {topIntents.slice(0, 5).map((item, index) => (
                <div
                  key={item.intent}
                  className="flex items-center gap-4 p-3 rounded-lg bg-zinc-50 dark:bg-zinc-700/50"
                >
                  <div className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold',
                    index === 0 && 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
                    index === 1 && 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
                    index === 2 && 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
                    index > 2 && 'bg-zinc-100 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300'
                  )}>
                    {index + 1}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-zinc-900 dark:text-white">
                      {intentTypeLabels[item.intent] || item.intent}
                    </p>
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {item.count.toLocaleString()} detecções
                    </p>
                  </div>
                  <CheckCircleIcon className="w-5 h-5 text-green-500" />
                </div>
              ))}
            </div>
          ) : (
            <p className="text-zinc-500 dark:text-zinc-400 text-center py-8">
              Nenhuma intenção registrada ainda.
            </p>
          )}
        </div>
      </div>

      {/* Method Comparison */}
      <div className="bg-white dark:bg-zinc-800 rounded-xl p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-zinc-900 dark:text-white mb-4">
          Comparação de Métodos
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="p-4 rounded-lg bg-green-50 dark:bg-green-900/20">
            <div className="flex items-center gap-3 mb-2">
              <BoltIcon className="w-6 h-6 text-green-600" />
              <h4 className="font-semibold text-green-900 dark:text-green-100">Regex (Pattern Matching)</h4>
            </div>
            <p className="text-sm text-green-700 dark:text-green-300 mb-2">
              Detecção rápida baseada em padrões predefinidos. Sem custo de API.
            </p>
            <ul className="text-sm text-green-600 dark:text-green-400 space-y-1">
              <li>• Velocidade: ~50ms</li>
              <li>• Custo: Gratuito</li>
              <li>• Cobertura: 80% dos casos</li>
            </ul>
          </div>
          <div className="p-4 rounded-lg bg-purple-50 dark:bg-purple-900/20">
            <div className="flex items-center gap-3 mb-2">
              <CpuChipIcon className="w-6 h-6 text-purple-600" />
              <h4 className="font-semibold text-purple-900 dark:text-purple-100">LLM (Inteligência Artificial)</h4>
            </div>
            <p className="text-sm text-purple-700 dark:text-purple-300 mb-2">
              Detecção avançada usando IA. Usado como fallback para casos complexos.
            </p>
            <ul className="text-sm text-purple-600 dark:text-purple-400 space-y-1">
              <li>• Velocidade: ~2000ms</li>
              <li>• Custo: Pago por chamada</li>
              <li>• Cobertura: Casos complexos</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default IntentStatsPage;
