/**
 * Reports Page - Analytics Dashboard
 * Professional reports with charts, filters, and export functionality
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Grid,
  Typography,
  Button,
  ButtonGroup,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  TextField,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
  IconButton,
  Tooltip,
  Divider,
  LinearProgress,
  useTheme,
  alpha
} from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import DownloadIcon from '@mui/icons-material/Download';
import RefreshIcon from '@mui/icons-material/Refresh';
import CalendarMonthIcon from '@mui/icons-material/CalendarMonth';
import ShoppingCartIcon from '@mui/icons-material/ShoppingCart';
import PeopleIcon from '@mui/icons-material/People';
import InventoryIcon from '@mui/icons-material/Inventory';
import AttachMoneyIcon from '@mui/icons-material/AttachMoney';
import WarningIcon from '@mui/icons-material/Warning';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import LocalShippingIcon from '@mui/icons-material/LocalShipping';
import StarIcon from '@mui/icons-material/Star';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  Area,
  AreaChart
} from 'recharts';
import { format, subDays, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import {
  reportsService,
  RevenueReport,
  ProductsReport,
  StockReport,
  CustomersReport,
  DashboardStats
} from '../../services/reports';

// =============================================================================
// TYPES
// =============================================================================

type Period = '7d' | '30d' | '90d' | '1y';
type GroupBy = 'day' | 'week' | 'month';
type TabValue = 'overview' | 'revenue' | 'products' | 'stock' | 'customers';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  change?: number;
  icon: React.ReactNode;
  color?: string;
  loading?: boolean;
}

// =============================================================================
// COMPONENTS
// =============================================================================

const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  change,
  icon,
  color = '#6366f1',
  loading
}) => {
  const theme = useTheme();
  
  return (
    <Card
      sx={{
        height: '100%',
        background: `linear-gradient(135deg, ${alpha(color, 0.1)} 0%, ${alpha(color, 0.05)} 100%)`,
        border: `1px solid ${alpha(color, 0.2)}`,
        transition: 'transform 0.2s, box-shadow 0.2s',
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: `0 8px 24px ${alpha(color, 0.2)}`
        }
      }}
    >
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              {title}
            </Typography>
            {loading ? (
              <CircularProgress size={24} />
            ) : (
              <Typography variant="h4" fontWeight="bold" color={color}>
                {value}
              </Typography>
            )}
            {subtitle && (
              <Typography variant="body2" color="text.secondary" mt={0.5}>
                {subtitle}
              </Typography>
            )}
            {change !== undefined && (
              <Box display="flex" alignItems="center" mt={1}>
                {change >= 0 ? (
                  <TrendingUpIcon sx={{ color: 'success.main', fontSize: 18, mr: 0.5 }} />
                ) : (
                  <TrendingDownIcon sx={{ color: 'error.main', fontSize: 18, mr: 0.5 }} />
                )}
                <Typography
                  variant="body2"
                  color={change >= 0 ? 'success.main' : 'error.main'}
                  fontWeight="medium"
                >
                  {change >= 0 ? '+' : ''}{change.toFixed(1)}%
                </Typography>
                <Typography variant="body2" color="text.secondary" ml={0.5}>
                  vs ontem
                </Typography>
              </Box>
            )}
          </Box>
          <Box
            sx={{
              p: 1.5,
              borderRadius: 2,
              bgcolor: alpha(color, 0.15),
              color: color
            }}
          >
            {icon}
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
};

const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format(value);
};

const formatNumber = (value: number): string => {
  return new Intl.NumberFormat('pt-BR').format(value);
};

// =============================================================================
// MAIN COMPONENT
// =============================================================================

const AnalyticsPage: React.FC = () => {
  const theme = useTheme();
  
  // State
  const [activeTab, setActiveTab] = useState<TabValue>('overview');
  const [period, setPeriod] = useState<Period>('30d');
  const [groupBy, setGroupBy] = useState<GroupBy>('day');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Data
  const [dashboardStats, setDashboardStats] = useState<DashboardStats | null>(null);
  const [revenueReport, setRevenueReport] = useState<RevenueReport | null>(null);
  const [productsReport, setProductsReport] = useState<ProductsReport | null>(null);
  const [stockReport, setStockReport] = useState<StockReport | null>(null);
  const [customersReport, setCustomersReport] = useState<CustomersReport | null>(null);
  
  // Colors for charts
  const COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];
  
  // Load data
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      const [stats, revenue, products, stock, customers] = await Promise.all([
        reportsService.getDashboardStats(),
        reportsService.getRevenueReport({ period, group_by: groupBy }),
        reportsService.getProductsReport({ period }),
        reportsService.getStockReport(),
        reportsService.getCustomersReport({ period })
      ]);
      
      setDashboardStats(stats);
      setRevenueReport(revenue);
      setProductsReport(products);
      setStockReport(stock);
      setCustomersReport(customers);
    } catch (err) {
      console.error('Failed to load reports:', err);
      setError('Erro ao carregar relatórios. Tente novamente.');
    } finally {
      setLoading(false);
    }
  }, [period, groupBy]);
  
  useEffect(() => {
    loadData();
  }, [loadData]);
  
  // Export handlers
  const handleExportOrders = async () => {
    try {
      const blob = await reportsService.exportOrdersCSV({ period });
      const filename = `pedidos_${format(new Date(), 'yyyy-MM-dd')}.csv`;
      reportsService.downloadBlob(blob, filename);
    } catch (err) {
      console.error('Export failed:', err);
    }
  };
  
  // Render Overview Tab
  const renderOverview = () => (
    <Box>
      {/* Stats Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Faturamento Hoje"
            value={formatCurrency(dashboardStats?.today.revenue || 0)}
            change={dashboardStats?.today.revenue_change_percent}
            icon={<AttachMoneyIcon />}
            color="#22c55e"
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Pedidos Hoje"
            value={dashboardStats?.today.orders || 0}
            subtitle={`${dashboardStats?.week.orders || 0} esta semana`}
            icon={<ShoppingCartIcon />}
            color="#6366f1"
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Pedidos Pendentes"
            value={dashboardStats?.alerts.pending_orders || 0}
            subtitle="Aguardando ação"
            icon={<LocalShippingIcon />}
            color="#f59e0b"
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Estoque Baixo"
            value={dashboardStats?.alerts.low_stock_products || 0}
            subtitle="Produtos para repor"
            icon={<WarningIcon />}
            color="#ef4444"
            loading={loading}
          />
        </Grid>
      </Grid>
      
      {/* Revenue Chart */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
            <Typography variant="h6" fontWeight="bold">
              Faturamento
            </Typography>
            <ButtonGroup size="small">
              <Button
                variant={groupBy === 'day' ? 'contained' : 'outlined'}
                onClick={() => setGroupBy('day')}
              >
                Dia
              </Button>
              <Button
                variant={groupBy === 'week' ? 'contained' : 'outlined'}
                onClick={() => setGroupBy('week')}
              >
                Semana
              </Button>
              <Button
                variant={groupBy === 'month' ? 'contained' : 'outlined'}
                onClick={() => setGroupBy('month')}
              >
                Mês
              </Button>
            </ButtonGroup>
          </Box>
          
          {loading ? (
            <Box display="flex" justifyContent="center" py={8}>
              <CircularProgress />
            </Box>
          ) : (
            <ResponsiveContainer width="100%" height={350}>
              <AreaChart data={revenueReport?.data || []}>
                <defs>
                  <linearGradient id="colorRevenue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={alpha(theme.palette.divider, 0.5)} />
                <XAxis
                  dataKey="period"
                  tickFormatter={(value) => {
                    try {
                      return format(parseISO(value), 'dd/MM', { locale: ptBR });
                    } catch {
                      return value;
                    }
                  }}
                  stroke={theme.palette.text.secondary}
                />
                <YAxis
                  tickFormatter={(value) => `R$ ${(value / 1000).toFixed(0)}k`}
                  stroke={theme.palette.text.secondary}
                />
                <RechartsTooltip
                  formatter={(value: number | undefined) => [formatCurrency(value ?? 0), 'Faturamento']}
                  labelFormatter={(label: string) => {
                    try {
                      return format(parseISO(label), "dd 'de' MMMM", { locale: ptBR });
                    } catch {
                      return label;
                    }
                  }}
                  contentStyle={{
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 8
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="total_revenue"
                  stroke="#6366f1"
                  strokeWidth={2}
                  fill="url(#colorRevenue)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
      
      {/* Two Column Layout */}
      <Grid container spacing={3}>
        {/* Top Products */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6" fontWeight="bold">
                  Produtos Mais Vendidos
                </Typography>
                <Chip label={`Top ${productsReport?.top_products.length || 0}`} size="small" />
              </Box>
              
              {loading ? (
                <LinearProgress />
              ) : (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Produto</TableCell>
                        <TableCell align="right">Qtd</TableCell>
                        <TableCell align="right">Receita</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {productsReport?.top_products.slice(0, 5).map((product, index) => (
                        <TableRow key={product.product_id || index}>
                          <TableCell>
                            <Box display="flex" alignItems="center" gap={1}>
                              {index < 3 && (
                                <StarIcon sx={{ color: index === 0 ? '#fbbf24' : index === 1 ? '#9ca3af' : '#cd7f32', fontSize: 16 }} />
                              )}
                              <Typography variant="body2" noWrap sx={{ maxWidth: 150 }}>
                                {product.product_name}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontWeight="medium">
                              {product.total_quantity}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" color="success.main" fontWeight="medium">
                              {formatCurrency(product.total_revenue)}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </Grid>
        
        {/* Customer Stats */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" mb={2}>
                Clientes
              </Typography>
              
              {loading ? (
                <LinearProgress />
              ) : (
                <Box>
                  <Grid container spacing={2} mb={3}>
                    <Grid item xs={6}>
                      <Box textAlign="center" p={2} bgcolor={alpha('#6366f1', 0.1)} borderRadius={2}>
                        <Typography variant="h4" fontWeight="bold" color="primary">
                          {customersReport?.summary.total_customers || 0}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Total de Clientes
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6}>
                      <Box textAlign="center" p={2} bgcolor={alpha('#22c55e', 0.1)} borderRadius={2}>
                        <Typography variant="h4" fontWeight="bold" color="success.main">
                          {customersReport?.summary.retention_rate || 0}%
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Taxa de Retenção
                        </Typography>
                      </Box>
                    </Grid>
                  </Grid>
                  
                  <Divider sx={{ my: 2 }} />
                  
                  <Box display="flex" justifyContent="space-between" mb={1}>
                    <Typography variant="body2" color="text.secondary">
                      Novos Clientes
                    </Typography>
                    <Typography variant="body2" fontWeight="medium">
                      {customersReport?.summary.new_customers || 0}
                    </Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      Clientes Recorrentes
                    </Typography>
                    <Typography variant="body2" fontWeight="medium">
                      {customersReport?.summary.returning_customers || 0}
                    </Typography>
                  </Box>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
  
  // Render Stock Tab
  const renderStock = () => (
    <Box>
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} sm={4}>
          <StatCard
            title="Total de Produtos"
            value={stockReport?.summary.total_products || 0}
            icon={<InventoryIcon />}
            color="#6366f1"
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <StatCard
            title="Estoque Baixo"
            value={stockReport?.summary.low_stock_count || 0}
            subtitle={`Limite: ${stockReport?.summary.low_stock_threshold || 10} unidades`}
            icon={<WarningIcon />}
            color="#f59e0b"
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <StatCard
            title="Sem Estoque"
            value={stockReport?.summary.out_of_stock_count || 0}
            subtitle="Reposição urgente"
            icon={<WarningIcon />}
            color="#ef4444"
            loading={loading}
          />
        </Grid>
      </Grid>
      
      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight="bold" mb={3}>
            Produtos com Estoque Baixo
          </Typography>
          
          {loading ? (
            <LinearProgress />
          ) : stockReport?.low_stock_products.length === 0 ? (
            <Alert severity="success" icon={<CheckCircleIcon />}>
              Todos os produtos estão com estoque adequado!
            </Alert>
          ) : (
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Produto</TableCell>
                    <TableCell>SKU</TableCell>
                    <TableCell>Categoria</TableCell>
                    <TableCell align="right">Estoque</TableCell>
                    <TableCell align="right">Preço</TableCell>
                    <TableCell>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {stockReport?.low_stock_products.map((product) => (
                    <TableRow key={product.id}>
                      <TableCell>
                        <Typography variant="body2" fontWeight="medium">
                          {product.name}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {product.sku || '-'}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip label={product.category || 'Sem categoria'} size="small" variant="outlined" />
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={product.stock_quantity || 0}
                          size="small"
                          color={product.stock_quantity === 0 ? 'error' : 'warning'}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2">
                          {formatCurrency(product.price)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={product.status === 'active' ? 'Ativo' : 'Inativo'}
                          size="small"
                          color={product.status === 'active' ? 'success' : 'default'}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>
    </Box>
  );
  
  return (
    <Box p={3}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={4}>
        <Box>
          <Typography variant="h4" fontWeight="bold" gutterBottom>
            Relatórios
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Análise completa do seu negócio
          </Typography>
        </Box>
        
        <Box display="flex" gap={2}>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Período</InputLabel>
            <Select
              value={period}
              label="Período"
              onChange={(e) => setPeriod(e.target.value as Period)}
            >
              <MenuItem value="7d">7 dias</MenuItem>
              <MenuItem value="30d">30 dias</MenuItem>
              <MenuItem value="90d">90 dias</MenuItem>
              <MenuItem value="1y">1 ano</MenuItem>
            </Select>
          </FormControl>
          
          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={handleExportOrders}
          >
            Exportar
          </Button>
          
          <IconButton onClick={loadData} disabled={loading}>
            <RefreshIcon />
          </IconButton>
        </Box>
      </Box>
      
      {/* Error Alert */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      
      {/* Tabs */}
      <Tabs
        value={activeTab}
        onChange={(_, value) => setActiveTab(value)}
        sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab label="Visão Geral" value="overview" />
        <Tab label="Faturamento" value="revenue" />
        <Tab label="Produtos" value="products" />
        <Tab label="Estoque" value="stock" />
        <Tab label="Clientes" value="customers" />
      </Tabs>
      
      {/* Tab Content */}
      {activeTab === 'overview' && renderOverview()}
      {activeTab === 'stock' && renderStock()}
      {activeTab === 'revenue' && renderOverview()}
      {activeTab === 'products' && renderOverview()}
      {activeTab === 'customers' && renderOverview()}
    </Box>
  );
};

export default AnalyticsPage;
