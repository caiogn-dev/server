/**
 * MessageInput - Input de mensagens moderno
 * 
 * Features:
 * - Auto-resize textarea
 * - Botões de anexo (imagem, documento)
 * - Preview de arquivos selecionados
 * - Send on Enter
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  PaperAirplaneIcon,
  PaperClipIcon,
  PhotoIcon,
  DocumentIcon,
  XMarkIcon,
  FaceSmileIcon,
} from '@heroicons/react/24/outline';

export interface MessageInputProps {
  onSend: (text: string) => void;
  onTyping?: (isTyping: boolean) => void;
  onFileSelect?: (file: File) => void;
  placeholder?: string;
  disabled?: boolean;
  isLoading?: boolean;
  showAttachment?: boolean;
  onAttachmentClick?: () => void;
  maxLength?: number;
  selectedFile?: File | null;
  onClearFile?: () => void;
}

export const MessageInput: React.FC<MessageInputProps> = ({
  onSend,
  onTyping,
  onFileSelect,
  placeholder = 'Digite uma mensagem...',
  disabled = false,
  isLoading = false,
  showAttachment = true,
  maxLength = 4096,
  selectedFile,
  onClearFile,
}) => {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const typingTimeoutRef = useRef<number | undefined>(undefined);
  const wasTypingRef = useRef(false);

  // Auto-resize textarea
  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    }
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [text, adjustHeight]);

  // Handle typing indicator
  const handleTyping = useCallback(() => {
    if (!onTyping) return;

    if (typingTimeoutRef.current) {
      window.clearTimeout(typingTimeoutRef.current);
    }

    if (!wasTypingRef.current) {
      wasTypingRef.current = true;
      onTyping(true);
    }

    typingTimeoutRef.current = window.setTimeout(() => {
      wasTypingRef.current = false;
      onTyping(false);
    }, 2000);
  }, [onTyping]);

  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) {
        window.clearTimeout(typingTimeoutRef.current);
      }
      if (wasTypingRef.current && onTyping) {
        onTyping(false);
      }
    };
  }, [onTyping]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    if (value.length <= maxLength) {
      setText(value);
      handleTyping();
    }
  };

  const handleSend = () => {
    const trimmedText = text.trim();
    if ((trimmedText || selectedFile) && !disabled && !isLoading) {
      onSend(trimmedText);
      setText('');
      
      if (typingTimeoutRef.current) {
        window.clearTimeout(typingTimeoutRef.current);
      }
      if (wasTypingRef.current && onTyping) {
        wasTypingRef.current = false;
        onTyping(false);
      }

      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onFileSelect) {
      onFileSelect(file);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const canSend = (text.trim().length > 0 || selectedFile) && !disabled && !isLoading;

  // Preview do arquivo selecionado
  const renderFilePreview = () => {
    if (!selectedFile) return null;

    const isImage = selectedFile.type.startsWith('image/');

    return (
      <div className="flex items-center gap-3 p-3 mx-4 mb-2 bg-gray-50 dark:bg-zinc-800 rounded-lg border border-gray-200 dark:border-zinc-700">
        {isImage ? (
          <PhotoIcon className="w-8 h-8 text-violet-500" />
        ) : (
          <DocumentIcon className="w-8 h-8 text-blue-500" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">
            {selectedFile.name}
          </p>
          <p className="text-xs text-gray-500">
            {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
          </p>
        </div>
        <button
          onClick={onClearFile}
          className="p-1 text-gray-400 hover:text-red-500 transition-colors"
        >
          <XMarkIcon className="w-5 h-5" />
        </button>
      </div>
    );
  };

  return (
    <div className="bg-white dark:bg-zinc-900">
      {/* Preview de arquivo */}
      {renderFilePreview()}

      {/* Input area */}
      <div className="flex items-end gap-2 p-3">
        {/* Botões de anexo */}
        {showAttachment && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className="p-2.5 text-gray-500 hover:text-violet-600 hover:bg-violet-50 dark:hover:bg-violet-900/20 rounded-full disabled:opacity-50 transition-colors"
              title="Anexar arquivo"
            >
              <PaperClipIcon className="w-5 h-5" />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,video/*,audio/*,application/pdf,.doc,.docx,.xls,.xlsx,.txt"
              onChange={handleFileSelect}
              className="hidden"
            />
          </div>
        )}

        {/* Textarea */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className="
              w-full resize-none rounded-full border border-gray-300 dark:border-zinc-600
              bg-white dark:bg-zinc-800 px-4 py-3 pr-12
              text-sm text-gray-900 dark:text-white
              placeholder-gray-400 dark:placeholder-zinc-500
              focus:ring-2 focus:ring-violet-500 focus:border-transparent
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-all min-h-[44px] max-h-[120px]
            "
          />
          
          {/* Character count */}
          {text.length > maxLength * 0.8 && (
            <span className={`absolute right-4 bottom-3 text-xs ${
              text.length >= maxLength ? 'text-red-500' : 'text-gray-400'
            }`}>
              {text.length}/{maxLength}
            </span>
          )}
        </div>

        {/* Emoji button */}
        <button
          type="button"
          disabled={disabled}
          className="p-2.5 text-gray-500 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded-full disabled:opacity-50 transition-colors hidden sm:block"
          title="Emoji"
        >
          <FaceSmileIcon className="w-5 h-5" />
        </button>

        {/* Send button */}
        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          className={`
            p-3 rounded-full transition-all
            ${canSend
              ? 'bg-violet-600 text-white hover:bg-violet-700 shadow-md hover:shadow-lg transform hover:scale-105'
              : 'bg-gray-200 dark:bg-zinc-700 text-gray-400 cursor-not-allowed'
            }
          `}
          title="Enviar"
        >
          {isLoading ? (
            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            <PaperAirplaneIcon className="w-5 h-5" />
          )}
        </button>
      </div>

      {/* Hint */}
      <p className="text-[10px] text-gray-400 pb-2 px-4 text-center hidden sm:block">
        Enter para enviar • Shift+Enter para nova linha
      </p>
    </div>
  );
};

export default MessageInput;
