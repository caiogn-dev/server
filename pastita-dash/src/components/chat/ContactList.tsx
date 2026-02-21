/**
 * ContactList - List of chat contacts/conversations
 * 
 * Displays a searchable list of conversations with:
 * - Contact avatar and name
 * - Last message preview
 * - Unread count badge
 * - Last activity time
 * - Status and mode indicators
 */
import React, { useState, useMemo } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import {
  MagnifyingGlassIcon,
  UserCircleIcon,
  ChatBubbleLeftIcon,
  FunnelIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

export interface Contact {
  id: string;
  phoneNumber: string;
  contactName: string;
  lastMessagePreview?: string;
  lastMessageAt?: string;
  unreadCount?: number;
  status?: string;
  mode?: 'auto' | 'human' | 'hybrid';
  isTyping?: boolean;
  isOnline?: boolean;
  profilePictureUrl?: string; // NOVO: URL da foto de perfil
}

export interface ContactListProps {
  contacts: Contact[];
  selectedContactId?: string;
  onSelectContact: (contact: Contact) => void;
  isLoading?: boolean;
  emptyMessage?: string;
}

const ContactAvatar: React.FC<{ 
  name: string; 
  phoneNumber: string;
  profilePictureUrl?: string;
}> = ({ name, phoneNumber, profilePictureUrl }) => {
  // NOVO: Se tem foto de perfil, mostra ela
  if (profilePictureUrl) {
    return (
      <img
        src={profilePictureUrl}
        alt={name || 'Contato'}
        className="w-12 h-12 rounded-full object-cover"
        onError={(e) => {
          // Se imagem falhar, esconde e mostra iniciais
          (e.target as HTMLImageElement).style.display = 'none';
        }}
      />
    );
  }
  
  // Comportamento existente: mostra iniciais
  const initials = name
    ? name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : phoneNumber.slice(-2);

  const colors = [
    'bg-blue-500',
    'bg-green-500',
    'bg-yellow-500',
    'bg-purple-500',
    'bg-pink-500',
    'bg-indigo-500',
    'bg-red-500',
    'bg-teal-500',
  ];

  // Generate consistent color based on phone number
  const colorIndex = phoneNumber.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % colors.length;
  const bgColor = colors[colorIndex];

  return (
    <div className={`w-12 h-12 rounded-full ${bgColor} flex items-center justify-center text-white font-semibold text-sm`}>
      {initials}
    </div>
  );
};

const ContactItem: React.FC<{
  contact: Contact;
  isSelected: boolean;
  onClick: () => void;
}> = ({ contact, isSelected, onClick }) => {
  const displayName = contact.contactName || contact.phoneNumber;
  const lastMessageTime = contact.lastMessageAt
    ? formatDistanceToNow(new Date(contact.lastMessageAt), { addSuffix: true, locale: ptBR })
    : '';

  return (
    <button
      onClick={onClick}
      className={`
        w-full flex items-center gap-3 p-3 text-left transition-colors
        ${isSelected
          ? 'bg-primary-50 dark:bg-primary-900/20 border-l-4 border-primary-500'
          : 'hover:bg-gray-50 dark:hover:bg-zinc-700/50 border-l-4 border-transparent'
        }
      `}
    >
      {/* Avatar */}
      <div className="relative flex-shrink-0">
        <ContactAvatar 
          name={contact.contactName} 
          phoneNumber={contact.phoneNumber}
          profilePictureUrl={contact.profilePictureUrl} // NOVO
        />
        {contact.unreadCount && contact.unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center font-medium">
            {contact.unreadCount > 9 ? '9+' : contact.unreadCount}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className={`font-medium truncate ${contact.unreadCount ? 'text-gray-900 dark:text-white' : 'text-gray-700 dark:text-zinc-300'}`}>
            {displayName}
          </span>
          <span className="text-xs text-gray-400 flex-shrink-0">
            {lastMessageTime}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          {contact.isTyping ? (
            <span className="text-sm text-primary-500 italic">Digitando...</span>
          ) : (
            <span className={`text-sm truncate ${contact.unreadCount ? 'text-gray-700 dark:text-gray-200 font-medium' : 'text-gray-500 dark:text-zinc-400'}`}>
              {contact.lastMessagePreview || 'Nenhuma mensagem'}
            </span>
          )}
        </div>
        {/* Mode indicator */}
        {contact.mode && (
          <span className={`
            inline-flex items-center mt-1 px-1.5 py-0.5 text-[10px] rounded-full
            ${contact.mode === 'human' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : ''}
            ${contact.mode === 'auto' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : ''}
            ${contact.mode === 'hybrid' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300' : ''}
          `}>
            {contact.mode === 'human' ? '👤 Humano' : contact.mode === 'auto' ? '🤖 Auto' : '🔄 Híbrido'}
          </span>
        )}
      </div>
    </button>
  );
};

export const ContactList: React.FC<ContactListProps> = ({
  contacts: rawContacts,
  selectedContactId,
  onSelectContact,
  isLoading = false,
  emptyMessage = 'Nenhuma conversa encontrada',
}) => {
  // Garantir que contacts sempre seja um array
  const contacts = rawContacts || [];
  
  const [searchQuery, setSearchQuery] = useState('');
  const [modeFilter, setModeFilter] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const filteredContacts = useMemo(() => {
    let result = contacts;
    
    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(contact =>
        contact.contactName?.toLowerCase().includes(query) ||
        contact.phoneNumber.includes(query) ||
        contact.lastMessagePreview?.toLowerCase().includes(query)
      );
    }
    
    // Apply mode filter
    if (modeFilter) {
      result = result.filter(contact => contact.mode === modeFilter);
    }
    
    return result;
  }, [contacts, searchQuery, modeFilter]);

  // Sort by last message time (most recent first), with unread at top
  const sortedContacts = useMemo(() => {
    return [...filteredContacts].sort((a, b) => {
      // Unread messages first
      if ((a.unreadCount || 0) > 0 && (b.unreadCount || 0) === 0) return -1;
      if ((a.unreadCount || 0) === 0 && (b.unreadCount || 0) > 0) return 1;
      
      // Then by last message time
      if (!a.lastMessageAt) return 1;
      if (!b.lastMessageAt) return -1;
      return new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime();
    });
  }, [filteredContacts]);

  // Count by mode
  const modeCounts = useMemo(() => {
    const counts = { human: 0, auto: 0, hybrid: 0 };
    contacts.forEach(c => {
      if (c.mode && counts[c.mode as keyof typeof counts] !== undefined) {
        counts[c.mode as keyof typeof counts]++;
      }
    });
    return counts;
  }, [contacts]);

  const totalUnread = useMemo(() => {
    return contacts.reduce((sum, c) => sum + (c.unreadCount || 0), 0);
  }, [contacts]);

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-900 border-r border-gray-200 dark:border-zinc-800">
      {/* Header with title and unread count */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-zinc-800 bg-gray-50 dark:bg-black">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 dark:text-white">Conversas</h3>
          {totalUnread > 0 && (
            <span className="px-2 py-0.5 bg-red-500 text-white text-xs rounded-full font-medium">
              {totalUnread} não lida{totalUnread !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Search and filter */}
      <div className="p-3 border-b border-gray-200 dark:border-zinc-800 space-y-2">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Buscar..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-gray-100 dark:bg-gray-700 border-0 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 dark:text-white"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
              >
                <XMarkIcon className="w-4 h-4" />
              </button>
            )}
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`p-2 rounded-lg transition-colors ${
              showFilters || modeFilter
                ? 'bg-primary-100 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-zinc-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
            title="Filtros"
          >
            <FunnelIcon className="w-5 h-5" />
          </button>
        </div>
        
        {/* Filter chips */}
        {showFilters && (
          <div className="flex flex-wrap gap-1">
            <button
              onClick={() => setModeFilter(null)}
              className={`px-2 py-1 text-xs rounded-full transition-colors ${
                !modeFilter
                  ? 'bg-primary-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400 hover:bg-gray-200'
              }`}
            >
              Todas ({contacts.length})
            </button>
            <button
              onClick={() => setModeFilter('human')}
              className={`px-2 py-1 text-xs rounded-full transition-colors ${
                modeFilter === 'human'
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400 hover:bg-gray-200'
              }`}
            >
              👤 Humano ({modeCounts.human})
            </button>
            <button
              onClick={() => setModeFilter('auto')}
              className={`px-2 py-1 text-xs rounded-full transition-colors ${
                modeFilter === 'auto'
                  ? 'bg-green-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-zinc-400 hover:bg-gray-200'
              }`}
            >
              🤖 Auto ({modeCounts.auto})
            </button>
          </div>
        )}
      </div>

      {/* Contact list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500 mb-2" />
            <span className="text-sm">Carregando...</span>
          </div>
        ) : sortedContacts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 p-4">
            <ChatBubbleLeftIcon className="w-12 h-12 mb-2" />
            <span className="text-sm text-center">
              {searchQuery || modeFilter ? 'Nenhuma conversa encontrada com os filtros aplicados' : emptyMessage}
            </span>
            {(searchQuery || modeFilter) && (
              <button
                onClick={() => { setSearchQuery(''); setModeFilter(null); }}
                className="mt-2 text-primary-500 text-sm hover:underline"
              >
                Limpar filtros
              </button>
            )}
          </div>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-700">
            {sortedContacts.map((contact) => (
              <ContactItem
                key={contact.id}
                contact={contact}
                isSelected={contact.id === selectedContactId}
                onClick={() => onSelectContact(contact)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer with count */}
      <div className="p-2 border-t border-gray-200 dark:border-zinc-800 text-center bg-gray-50 dark:bg-black">
        <span className="text-xs text-gray-400">
          {sortedContacts.length} de {contacts.length} conversa{contacts.length !== 1 ? 's' : ''}
        </span>
      </div>
    </div>
  );
};

export default ContactList;
