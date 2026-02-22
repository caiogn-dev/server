import React, { useState } from 'react';
import { whatsappTemplates, getTemplatesByCategory, WhatsAppTemplate } from '../../../data/whatsappTemplates';
import { Badge } from '../../../components/common';
import type { BadgeProps } from '../../../components/common/Badge';

const WhatsAppTemplatesPage: React.FC = () => {
  const [selectedCategory, setSelectedCategory] = useState<'all' | 'transactional' | 'marketing' | 'support'>('all');
  const [selectedTemplate, setSelectedTemplate] = useState<WhatsAppTemplate | null>(null);
  const [previewVariables, setPreviewVariables] = useState<Record<string, string>>({});

  const filteredTemplates = selectedCategory === 'all' 
    ? whatsappTemplates 
    : getTemplatesByCategory(selectedCategory);

  const getCategoryVariant = (category: WhatsAppTemplate['category']): BadgeProps['variant'] => {
    switch (category) {
      case 'transactional': return 'info';
      case 'marketing': return 'purple';
      case 'support': return 'success';
      default: return 'gray';
    }
  };

  const getCategoryLabel = (category: WhatsAppTemplate['category']) => {
    switch (category) {
      case 'transactional': return 'Transacional';
      case 'marketing': return 'Marketing';
      case 'support': return 'Suporte';
      default: return category;
    }
  };

  const handleTemplateSelect = (template: WhatsAppTemplate) => {
    setSelectedTemplate(template);
    const vars: Record<string, string> = {};
    template.variables.forEach(v => {
      vars[v] = '';
    });
    setPreviewVariables(vars);
  };

  const getPreviewContent = () => {
    if (!selectedTemplate) return '';
    let content = selectedTemplate.content;
    Object.entries(previewVariables).forEach(([key, value]) => {
      content = content.replace(new RegExp(`{{${key}}}`, 'g'), value || `{{${key}}}`);
    });
    return content;
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Templates WhatsApp</h1>
        <p className="text-gray-600">Gerencie templates de mensagens para disparos automatizados</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-2xl font-bold text-gray-900">{whatsappTemplates.length}</div>
          <div className="text-sm text-gray-500">Total Templates</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-2xl font-bold text-blue-600">
            {getTemplatesByCategory('transactional').length}
          </div>
          <div className="text-sm text-gray-500">Transacionais</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-2xl font-bold text-purple-600">
            {getTemplatesByCategory('marketing').length}
          </div>
          <div className="text-sm text-gray-500">Marketing</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-2xl font-bold text-green-600">
            {getTemplatesByCategory('support').length}
          </div>
          <div className="text-sm text-gray-500">Suporte</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-8">
        {/* Templates List */}
        <div>
          {/* Filters */}
          <div className="flex gap-2 mb-4">
            {(['all', 'transactional', 'marketing', 'support'] as const).map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  selectedCategory === cat
                    ? 'bg-violet-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {cat === 'all' ? 'Todos' : getCategoryLabel(cat)}
              </button>
            ))}
          </div>

          {/* Templates Grid */}
          <div className="space-y-3">
            {filteredTemplates.map((template) => (
              <div
                key={template.id}
                onClick={() => handleTemplateSelect(template)}
                className={`p-4 rounded-lg border-2 cursor-pointer transition-all hover:shadow-md ${
                  selectedTemplate?.id === template.id
                    ? 'border-violet-500 bg-violet-50'
                    : 'border-gray-200 bg-white'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold text-gray-900">{template.name}</h3>
                  <Badge variant={getCategoryVariant(template.category)}>
                    {getCategoryLabel(template.category)}
                  </Badge>
                </div>
                <p className="text-sm text-gray-600 mb-3">{template.description}</p>
                <div className="flex flex-wrap gap-1">
                  {template.variables.map((variable) => (
                    <span
                      key={variable}
                      className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded"
                    >
                      {`{{${variable}}}`}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Preview Panel */}
        <div>
          {selectedTemplate ? (
            <div className="bg-white rounded-lg shadow-lg border border-gray-200 sticky top-6">
              <div className="p-4 border-b border-gray-200 bg-gray-50 rounded-t-lg">
                <h2 className="font-semibold text-gray-900">Preview</h2>
                <p className="text-sm text-gray-500">{selectedTemplate.name}</p>
              </div>

              {/* Variables Input */}
              <div className="p-4 border-b border-gray-200">
                <h3 className="text-sm font-medium text-gray-700 mb-3">Variáveis</h3>
                <div className="space-y-3">
                  {selectedTemplate.variables.map((variable) => (
                    <div key={variable}>
                      <label className="block text-xs text-gray-500 mb-1 capitalize">
                        {variable}
                      </label>
                      <input
                        type="text"
                        value={previewVariables[variable] || ''}
                        onChange={(e) => setPreviewVariables(prev => ({
                          ...prev,
                          [variable]: e.target.value
                        }))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-violet-500 focus:border-violet-500"
                        placeholder={`Valor para {{${variable}}}`}
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* WhatsApp Preview */}
              <div className="p-4 bg-[#e5ddd5] min-h-[300px]">
                <div className="bg-white rounded-lg rounded-tl-none shadow-sm p-3 max-w-[90%] relative">
                  <div className="absolute -left-2 top-0 w-0 h-0 border-t-[10px] border-t-transparent border-r-[10px] border-r-white border-b-[10px] border-b-transparent"></div>
                  <pre className="text-sm text-gray-800 whitespace-pre-wrap font-sans">
                    {getPreviewContent()}
                  </pre>
                  <div className="text-right mt-1">
                    <span className="text-xs text-gray-400">{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="p-4 border-t border-gray-200 flex gap-3">
                <button className="flex-1 bg-violet-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-violet-700 transition-colors">
                  Usar Template
                </button>
                <button className="px-4 py-2 border border-gray-300 rounded-lg font-medium text-gray-700 hover:bg-gray-50 transition-colors">
                  Editar
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 rounded-lg border-2 border-dashed border-gray-300 p-12 text-center">
              <div className="text-4xl mb-4">📱</div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">Selecione um template</h3>
              <p className="text-gray-500">Clique em um template à esquerda para visualizar</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default WhatsAppTemplatesPage;
