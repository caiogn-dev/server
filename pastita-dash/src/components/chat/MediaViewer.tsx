/**
 * MediaViewer - Modal para visualizar imagens, vídeos e documentos
 */
import React from 'react';
import {
  XMarkIcon,
  ArrowDownTrayIcon,
  PhotoIcon,
  DocumentIcon,
  FilmIcon,
} from '@heroicons/react/24/outline';

export interface MediaViewerProps {
  url: string;
  type: string;
  fileName?: string;
  onClose: () => void;
}

export const MediaViewer: React.FC<MediaViewerProps> = ({
  url,
  type,
  fileName,
  onClose,
}) => {
  const isImage = type.startsWith('image/') || ['image', 'sticker'].includes(type);
  const isVideo = type.startsWith('video/') || type === 'video';
  const isAudio = type.startsWith('audio/') || type === 'audio';
  const isDocument = !isImage && !isVideo && !isAudio;

  const handleDownload = () => {
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName || 'download';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Header */}
      <div className="absolute top-0 left-0 right-0 flex items-center justify-between p-4 bg-gradient-to-b from-black/80 to-transparent">
        <div className="flex items-center gap-3 text-white">
          {isImage && <PhotoIcon className="w-6 h-6" />}
          {isVideo && <FilmIcon className="w-6 h-6" />}
          {isDocument && <DocumentIcon className="w-6 h-6" />}
          <span className="text-sm font-medium truncate max-w-md">
            {fileName || 'Visualizador de Mídia'}
          </span>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleDownload();
            }}
            className="p-2 text-white/80 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
            title="Baixar"
          >
            <ArrowDownTrayIcon className="w-6 h-6" />
          </button>
          <button
            onClick={onClose}
            className="p-2 text-white/80 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
            title="Fechar"
          >
            <XMarkIcon className="w-6 h-6" />
          </button>
        </div>
      </div>

      {/* Conteúdo */}
      <div 
        className="max-w-[90vw] max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {isImage && (
          <img
            src={url}
            alt={fileName || 'Imagem'}
            className="max-w-full max-h-[85vh] object-contain rounded-lg"
          />
        )}

        {isVideo && (
          <video
            src={url}
            controls
            className="max-w-full max-h-[85vh] rounded-lg"
            autoPlay
          />
        )}

        {isAudio && (
          <div className="bg-white dark:bg-zinc-800 rounded-lg p-8">
            <audio src={url} controls className="w-96" />
          </div>
        )}

        {isDocument && (
          <div className="bg-white dark:bg-zinc-800 rounded-lg p-8 text-center">
            <DocumentIcon className="w-24 h-24 text-gray-400 mx-auto mb-4" />
            <p className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              {fileName || 'Documento'}
            </p>
            <p className="text-sm text-gray-500 mb-4">
              Este arquivo não pode ser visualizado diretamente
            </p>
            <button
              onClick={handleDownload}
              className="inline-flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition-colors"
            >
              <ArrowDownTrayIcon className="w-5 h-5" />
              Baixar Arquivo
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default MediaViewer;
