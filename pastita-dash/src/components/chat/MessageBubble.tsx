/**
 * MessageBubble - Balão de mensagem do chat
 * 
 * Suporta:
 * - Texto, imagem, vídeo, áudio, documento
 * - Status de entrega
 * - Preview de mídia clicável
 * - Download de documentos
 */
import React from 'react';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import {
  CheckIcon,
  ClockIcon,
  ExclamationCircleIcon,
  PhotoIcon,
  DocumentIcon,
  MapPinIcon,
  UserIcon,
  ShoppingCartIcon,
  PlayIcon,
  ArrowDownTrayIcon,
} from '@heroicons/react/24/outline';
import { CheckIcon as CheckIconSolid } from '@heroicons/react/24/solid';

export interface MessageBubbleProps {
  id: string;
  direction: 'inbound' | 'outbound';
  messageType: string;
  status: 'pending' | 'sent' | 'delivered' | 'read' | 'failed';
  textBody: string;
  content?: Record<string, unknown>;
  mediaUrl?: string;
  mediaType?: string;
  fileName?: string;
  createdAt: string;
  sentAt?: string;
  deliveredAt?: string;
  readAt?: string;
  errorMessage?: string;
  onMediaClick?: (url: string, type: string, fileName?: string) => void;
}

const StatusIndicator: React.FC<{ status: string }> = ({ status }) => {
  switch (status) {
    case 'pending':
      return <ClockIcon className="w-3.5 h-3.5 text-gray-400" title="Pendente" />;
    case 'sent':
      return <CheckIcon className="w-3.5 h-3.5 text-gray-400" title="Enviado" />;
    case 'delivered':
      return (
        <div className="flex -space-x-1" title="Entregue">
          <CheckIcon className="w-3.5 h-3.5 text-gray-400" />
          <CheckIcon className="w-3.5 h-3.5 text-gray-400" />
        </div>
      );
    case 'read':
      return (
        <div className="flex -space-x-1" title="Lido">
          <CheckIconSolid className="w-3.5 h-3.5 text-blue-500" />
          <CheckIconSolid className="w-3.5 h-3.5 text-blue-500" />
        </div>
      );
    case 'failed':
      return <ExclamationCircleIcon className="w-3.5 h-3.5 text-red-500" title="Falhou" />;
    default:
      return null;
  }
};

const MediaPreview: React.FC<{
  type: string;
  url?: string;
  fileName?: string;
  content?: Record<string, unknown>;
  onClick?: () => void;
}> = ({ type, url, fileName, content, onClick }) => {
  // Imagem
  if ((type === 'image' || type === 'sticker') && url) {
    return (
      <div 
        className="relative group cursor-pointer mb-2 overflow-hidden rounded-lg"
        onClick={onClick}
      >
        <img
          src={url}
          alt="Imagem"
          className="max-w-[280px] max-h-[200px] object-cover rounded-lg hover:opacity-90 transition-opacity"
        />
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center">
          <PhotoIcon className="w-8 h-8 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      </div>
    );
  }

  // Vídeo
  if (type === 'video' && url) {
    return (
      <div 
        className="relative group cursor-pointer mb-2 overflow-hidden rounded-lg"
        onClick={onClick}
      >
        <video
          src={url}
          className="max-w-[280px] max-h-[200px] object-cover rounded-lg"
        />
        <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/40 transition-colors">
          <div className="w-12 h-12 bg-white/80 rounded-full flex items-center justify-center">
            <PlayIcon className="w-6 h-6 text-gray-800 ml-1" />
          </div>
        </div>
      </div>
    );
  }

  // Áudio
  if (type === 'audio' && url) {
    return (
      <div className="w-[260px] mb-2">
        <audio src={url} controls className="w-full h-10" />
      </div>
    );
  }

  // Documento
  if (type === 'document') {
    return (
      <div 
        className="flex items-center gap-3 p-3 bg-gray-100/50 dark:bg-black/20 rounded-lg mb-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-black/30 transition-colors max-w-[280px]"
        onClick={onClick}
      >
        <div className="w-10 h-10 bg-violet-100 dark:bg-violet-900/30 rounded-lg flex items-center justify-center flex-shrink-0">
          <DocumentIcon className="w-5 h-5 text-violet-600 dark:text-violet-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">
            {fileName || 'Documento'}
          </p>
          <p className="text-xs text-gray-500">Clique para baixar</p>
        </div>
        <ArrowDownTrayIcon className="w-4 h-4 text-gray-400" />
      </div>
    );
  }

  // Localização
  if (type === 'location') {
    const location = content?.location as { latitude?: number; longitude?: number; name?: string } | undefined;
    const mapsUrl = location?.latitude && location?.longitude
      ? `https://www.google.com/maps?q=${location.latitude},${location.longitude}`
      : '#';
    
    return (
      <a
        href={mapsUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-3 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg mb-2 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors max-w-[280px]"
      >
        <MapPinIcon className="w-8 h-8 text-red-500 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
            {location?.name || 'Localização'}
          </p>
          <p className="text-xs text-red-600 dark:text-red-400">Abrir no Maps</p>
        </div>
      </a>
    );
  }

  // Contato
  if (type === 'contacts') {
    const contentData = content as { contacts?: Array<{ name?: { formatted_name?: string }; phones?: Array<{ phone?: string }> }> } | undefined;
    const contact = contentData?.contacts?.[0];
    return (
      <div className="flex items-center gap-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg mb-2 max-w-[280px]">
        <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center">
          <UserIcon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
            {contact?.name?.formatted_name || 'Contato'}
          </p>
          {contact?.phones?.[0]?.phone && (
            <p className="text-xs text-gray-500">{contact.phones[0].phone}</p>
          )}
        </div>
      </div>
    );
  }

  // Pedido
  if (type === 'order') {
    return (
      <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg mb-2 max-w-[280px]">
        <ShoppingCartIcon className="w-8 h-8 text-green-500" />
        <span className="text-sm font-medium text-gray-700 dark:text-gray-200">Pedido</span>
      </div>
    );
  }

  return null;
};

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  direction,
  messageType,
  status,
  textBody,
  content,
  mediaUrl,
  mediaType,
  fileName,
  createdAt,
  errorMessage,
  onMediaClick,
}) => {
  const isOutbound = direction === 'outbound';
  const hasMedia = ['image', 'video', 'audio', 'document', 'sticker', 'location', 'contacts', 'order'].includes(messageType);

  return (
    <div className={`flex ${isOutbound ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`
          max-w-[80%] sm:max-w-[70%] rounded-2xl shadow-sm
          ${isOutbound
            ? 'bg-[#dcf8c6] dark:bg-emerald-800/80 text-gray-800 dark:text-white rounded-br-sm'
            : 'bg-white dark:bg-zinc-800 text-gray-800 dark:text-white rounded-bl-sm'
          }
        `}
      >
        {/* Mídia */}
        {hasMedia && (
          <div className="p-1">
            <MediaPreview
              type={messageType}
              url={mediaUrl}
              fileName={fileName}
              content={content}
              onClick={() => mediaUrl && onMediaClick?.(mediaUrl, mediaType || messageType, fileName)}
            />
          </div>
        )}

        {/* Texto */}
        {textBody && (
          <div className="px-3 pb-1">
            <p className="text-sm whitespace-pre-wrap break-words leading-relaxed">
              {textBody}
            </p>
          </div>
        )}

        {/* Erro */}
        {status === 'failed' && errorMessage && (
          <p className="px-3 text-xs text-red-500 mt-1">{errorMessage}</p>
        )}

        {/* Timestamp e Status */}
        <div className={`flex items-center justify-end gap-1 px-3 pb-1.5 pt-1 ${
          isOutbound ? 'text-gray-500 dark:text-gray-300' : 'text-gray-400'
        }`}>
          <span className="text-[11px]">
            {format(new Date(createdAt), 'HH:mm', { locale: ptBR })}
          </span>
          {isOutbound && <StatusIndicator status={status} />}
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;
