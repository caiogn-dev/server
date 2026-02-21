// @ts-nocheck
/**
 * Instagram Dashboard Page
 * 
 * Dashboard completo do Instagram com:
 * - Feed de posts
 * - Stories
 * - Reels
 * - Estatísticas
 * - Acesso rápido a Lives e Shopping
 */
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  PhotoIcon,
  VideoCameraIcon,
  PlayIcon,
  ShoppingBagIcon,
  RadioIcon,
  PlusIcon,
  CalendarIcon,
  ChartBarIcon,
  HeartIcon,
  ChatBubbleLeftIcon,
  BookmarkIcon,
  ShareIcon,
  EyeIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Card, Button, Loading, Tabs, StatCard, Badge } from '@/components/common';
import { 
  instagramAccountApi, 
  instagramMediaApi, 
  InstagramAccount, 
  InstagramMedia 
} from '@/services';
import { useFetch } from '@/hooks';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';

type TabType = 'feed' | 'stories' | 'reels' | 'insights';

export const InstagramDashboardPage: React.FC = () => {
  const { accountId } = useParams<{ accountId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabType>('feed');
  const [isCreating, setIsCreating] = useState(false);

  // Fetch account data
  const { 
    data: account, 
    loading: accountLoading 
  } = useFetch(
    () => instagramAccountApi.get(accountId!),
    { enabled: !!accountId }
  );

  // Fetch media based on tab
  const fetchMedia = async () => {
    if (!accountId) return [];
    switch (activeTab) {
      case 'feed':
        return instagramMediaApi.getFeed();
      case 'stories':
        return instagramMediaApi.getStories();
      case 'reels':
        return instagramMediaApi.getReels();
      default:
        return [];
    }
  };

  const { 
    data: media, 
    loading: mediaLoading,
    refresh: refreshMedia 
  } = useFetch(fetchMedia, { deps: [activeTab, accountId] });

  const handleCreatePost = () => {
    navigate(`/instagram/${accountId}/create`, { 
      state: { mediaType: activeTab === 'reels' ? 'REELS' : 'IMAGE' }
    });
  };

  const handleSchedulePost = () => {
    navigate(`/instagram/${accountId}/schedule`);
  };

  if (accountLoading) {
    return (
      <div className="p-6">
        <Loading message="Carregando conta..." />
      </div>
    );
  }

  if (!account) {
    return (
      <div className="p-6">
        <Card>
          <div className="text-center py-8">
            <p className="text-gray-500">Conta não encontrada</p>
            <Button 
              onClick={() => navigate('/instagram')}
              variant="primary"
              className="mt-4"
            >
              Voltar para Contas
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const tabs = [
    { id: 'feed', label: 'Feed', icon: PhotoIcon },
    { id: 'stories', label: 'Stories', icon: VideoCameraIcon },
    { id: 'reels', label: 'Reels', icon: PlayIcon },
    { id: 'insights', label: 'Estatísticas', icon: ChartBarIcon },
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Header com Info da Conta */}
      <Card className="overflow-hidden">
        <div className="bg-gradient-to-r from-purple-600 via-pink-500 to-orange-400 p-6">
          <div className="flex flex-col md:flex-row items-center gap-6">
            {/* Avatar */}
            <div className="relative">
              {account.profile_picture_url ? (
                <img
                  src={account.profile_picture_url}
                  alt={account.username}
                  className="w-24 h-24 rounded-full border-4 border-white shadow-lg object-cover"
                />
              ) : (
                <div className="w-24 h-24 rounded-full border-4 border-white shadow-lg bg-gradient-to-br from-purple-400 to-pink-400 flex items-center justify-center">
                  <span className="text-3xl text-white font-bold">
                    {account.username[0].toUpperCase()}
                  </span>
                </div>
              )}
              {account.is_verified && (
                <div className="absolute -bottom-1 -right-1 w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center border-2 border-white">
                  <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
              )}
            </div>

            {/* Info */}
            <div className="text-center md:text-left text-white">
              <h1 className="text-2xl font-bold">@{account.username}</h1>
              <p className="mt-1 opacity-90">{account.biography || 'Sem biografia'}</p>
              
              <div className="flex flex-wrap justify-center md:justify-start gap-6 mt-4">
                <div>
                  <span className="text-2xl font-bold">
                    {account.media_count.toLocaleString('pt-BR')}
                  </span>
                  <span className="block text-sm opacity-80">publicações</span>
                </div>
                <div>
                  <span className="text-2xl font-bold">
                    {account.followers_count.toLocaleString('pt-BR')}
                  </span>
                  <span className="block text-sm opacity-80">seguidores</span>
                </div>
                <div>
                  <span className="text-2xl font-bold">
                    {account.follows_count.toLocaleString('pt-BR')}
                  </span>
                  <span className="block text-sm opacity-80">seguindo</span>
                </div>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="flex flex-wrap justify-center gap-3">
              <Button
                onClick={() => navigate(`/instagram/${accountId}/live`)}
                variant="secondary"
                className="bg-white/20 backdrop-blur-sm text-white border-white/30 hover:bg-white/30"
                leftIcon={<RadioIcon className="w-5 h-5" />}
              >
                Live
              </Button>
              <Button
                onClick={() => navigate(`/instagram/${accountId}/shopping`)}
                variant="secondary"
                className="bg-white/20 backdrop-blur-sm text-white border-white/30 hover:bg-white/30"
                leftIcon={<ShoppingBagIcon className="w-5 h-5" />}
              >
                Shopping
              </Button>
              <Button
                onClick={() => navigate(`/instagram/${accountId}/schedule`)}
                variant="secondary"
                className="bg-white/20 backdrop-blur-sm text-white border-white/30 hover:bg-white/30"
                leftIcon={<CalendarIcon className="w-5 h-5" />}
              >
                Agendar
              </Button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700">
          <nav className="flex -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as TabType)}
                className={`
                  flex items-center gap-2 px-6 py-4 text-sm font-medium border-b-2 transition-colors
                  ${activeTab === tab.id
                    ? 'border-pink-500 text-pink-600 dark:text-pink-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }
                `}
              >
                <tab.icon className="w-5 h-5" />
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </Card>

      {/* Content */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">
          {activeTab === 'feed' && 'Feed de Posts'}
          {activeTab === 'stories' && 'Stories'}
          {activeTab === 'reels' && 'Reels'}
          {activeTab === 'insights' && 'Estatísticas'}
        </h2>
        
        {activeTab !== 'insights' && (
          <div className="flex gap-3">
            <Button
              onClick={handleSchedulePost}
              variant="secondary"
              leftIcon={<CalendarIcon className="w-5 h-5" />}
            >
              Agendar
            </Button>
            <Button
              onClick={handleCreatePost}
              variant="primary"
              leftIcon={<PlusIcon className="w-5 h-5" />}
            >
              Criar {activeTab === 'stories' ? 'Story' : activeTab === 'reels' ? 'Reel' : 'Post'}
            </Button>
          </div>
        )}
      </div>

      {/* Tab Content */}
      {mediaLoading ? (
        <Loading message="Carregando..." />
      ) : activeTab === 'insights' ? (
        <InstagramInsights accountId={accountId!} />
      ) : (
        <MediaGrid 
          media={media || []} 
          type={activeTab}
          onRefresh={refreshMedia}
        />
      )}
    </div>
  );
};

// ============================================================================
// MEDIA GRID COMPONENT
// ============================================================================

interface MediaGridProps {
  media: InstagramMedia[];
  type: TabType;
  onRefresh: () => void;
}

const MediaGrid: React.FC<MediaGridProps> = ({ media, type, onRefresh }) => {
  const navigate = useNavigate();

  if (media.length === 0) {
    return (
      <Card>
        <div className="p-12 text-center">
          <PhotoIcon className="w-16 h-16 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Nenhuma mídia encontrada
          </h3>
          <p className="text-gray-500 mb-4">
            {type === 'stories' && 'Você ainda não tem stories publicados'}
            {type === 'reels' && 'Você ainda não tem reels publicados'}
            {type === 'feed' && 'Você ainda não tem posts no feed'}
          </p>
          <Button onClick={onRefresh} variant="secondary">
            <ArrowPathIcon className="w-5 h-5 mr-2" />
            Atualizar
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <div className={`
      grid gap-4
      ${type === 'stories' 
        ? 'grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8' 
        : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
      }
    `}>
      {media.map((item) => (
        <div
          key={item.id}
          onClick={() => navigate(`/instagram/media/${item.id}`)}
          className="group relative aspect-square bg-gray-100 dark:bg-gray-800 rounded-lg overflow-hidden cursor-pointer"
        >
          {/* Thumbnail */}
          {item.thumbnail_url || item.media_url ? (
            <img
              src={item.thumbnail_url || item.media_url}
              alt={item.caption || 'Mídia'}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <PhotoIcon className="w-12 h-12 text-gray-400" />
            </div>
          )}

          {/* Overlay */}
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center text-white">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <HeartIcon className="w-5 h-5" />
                {item.likes_count}
              </span>
              <span className="flex items-center gap-1">
                <ChatBubbleLeftIcon className="w-5 h-5" />
                {item.comments_count}
              </span>
            </div>
          </div>

          {/* Badges */}
          <div className="absolute top-2 left-2 flex gap-1">
            {item.media_type === 'CAROUSEL_ALBUM' && (
              <Badge variant="secondary" className="bg-black/50 text-white">
                📎
              </Badge>
            )}
            {item.media_type === 'VIDEO' && (
              <Badge variant="secondary" className="bg-black/50 text-white">
                ▶️
              </Badge>
            )}
            {item.media_type === 'REELS' && (
              <Badge variant="secondary" className="bg-black/50 text-white">
                🎬
              </Badge>
            )}
          </div>

          {/* Status */}
          <div className="absolute top-2 right-2">
            {item.status === 'SCHEDULED' && (
              <Badge variant="warning">⏰ Agendado</Badge>
            )}
            {item.status === 'DRAFT' && (
              <Badge variant="secondary">📝 Rascunho</Badge>
            )}
          </div>

          {/* Caption (apenas para feed) */}
          {type === 'feed' && item.caption && (
            <div className="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-black/70 to-transparent">
              <p className="text-white text-xs line-clamp-2">{item.caption}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

// ============================================================================
// INSIGHTS COMPONENT
// ============================================================================

const InstagramInsights: React.FC<{ accountId: string }> = ({ accountId }) => {
  const [days, setDays] = useState(30);
  
  const { data: insights, loading } = useFetch(
    () => instagramAccountApi.getInsights(accountId, days),
    { deps: [accountId, days] }
  );

  if (loading) return <Loading />;

  return (
    <div className="space-y-6">
      {/* Period Selector */}
      <div className="flex justify-end">
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="px-4 py-2 border border-gray-300 rounded-lg"
        >
          <option value={7}>Últimos 7 dias</option>
          <option value={30}>Últimos 30 dias</option>
          <option value={90}>Últimos 90 dias</option>
        </select>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          title="Alcance"
          value={insights?.reduce((sum, i) => sum + i.reach, 0).toLocaleString('pt-BR') || '0'}
          icon={<EyeIcon className="w-5 h-5" />}
        />
        <StatCard
          title="Impressões"
          value={insights?.reduce((sum, i) => sum + i.impressions, 0).toLocaleString('pt-BR') || '0'}
          icon={<ChartBarIcon className="w-5 h-5" />}
        />
        <StatCard
          title="Engajamento"
          value={insights?.reduce((sum, i) => sum + i.engagement, 0).toLocaleString('pt-BR') || '0'}
          icon={<HeartIcon className="w-5 h-5" />}
        />
        <StatCard
          title="Novos Seguidores"
          value={insights?.reduce((sum, i) => sum + i.followers_gained, 0).toLocaleString('pt-BR') || '0'}
          icon={<ShareIcon className="w-5 h-5" />}
        />
      </div>

      {/* Chart placeholder - would use Chart.js in real implementation */}
      <Card>
        <div className="p-6">
          <h3 className="text-lg font-semibold mb-4">Visão Geral</h3>
          <div className="h-64 bg-gray-100 dark:bg-gray-800 rounded-lg flex items-center justify-center">
            <p className="text-gray-500">Gráfico de desempenho (implementar com Chart.js)</p>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default InstagramDashboardPage;
