/**
 * Products Page - Modern Multi-Tenant Catalog Management
 * 
 * Features:
 * - Store-scoped product management
 * - Dynamic product types with custom fields
 * - Categories management
 * - Rich product editor with image upload
 * - Grid and list views
 * - Advanced filtering and search
 * - Bulk actions
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  PlusIcon,
  MagnifyingGlassIcon,
  Squares2X2Icon,
  ListBulletIcon,
  FunnelIcon,
  ArrowPathIcon,
  PencilIcon,
  TrashIcon,
  DocumentDuplicateIcon,
  StarIcon,
  EyeIcon,
  EyeSlashIcon,
  PhotoIcon,
  TagIcon,
  CubeIcon,
  ChevronDownIcon,
  XMarkIcon,
  CheckIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid';
import toast from 'react-hot-toast';
import { Card, Button, Input, Badge, Modal, Loading } from '../../components/common';
import { useStore } from '../../hooks';
import storesApi, {
  StoreProduct as Product,
  StoreProductInput as ProductInput,
  StoreCategory as Category,
  StoreProductType as ProductType,
  CustomField,
} from '../../services/storesApi';
import logger from '../../services/logger';

type ViewMode = 'grid' | 'list';

// =============================================================================
// HELPER COMPONENTS
// =============================================================================

const formatMoney = (value: number) => {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
};

const StockBadge: React.FC<{ quantity: number; threshold?: number }> = ({ quantity, threshold = 5 }) => {
  if (quantity <= 0) {
    return <Badge variant="danger">Sem estoque</Badge>;
  }
  if (quantity <= threshold) {
    return <Badge variant="warning">Estoque baixo ({quantity})</Badge>;
  }
  return <Badge variant="success">{quantity} em estoque</Badge>;
};

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const variants: Record<string, 'success' | 'warning' | 'danger' | 'gray'> = {
    active: 'success',
    inactive: 'gray',
    out_of_stock: 'danger',
    discontinued: 'warning',
  };
  const labels: Record<string, string> = {
    active: 'Ativo',
    inactive: 'Inativo',
    out_of_stock: 'Sem Estoque',
    discontinued: 'Descontinuado',
  };
  return <Badge variant={variants[status] || 'gray'}>{labels[status] || status}</Badge>;
};

// =============================================================================
// PRODUCT CARD COMPONENT
// =============================================================================

interface ProductCardProps {
  product: Product;
  onEdit: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onToggleFeatured: () => void;
  onToggleStatus: () => void;
}

const ProductCard: React.FC<ProductCardProps> = ({
  product,
  onEdit,
  onDelete,
  onDuplicate,
  onToggleFeatured,
  onToggleStatus,
}) => {
  const imageUrl = product.main_image_url || product.main_image;
  
  return (
    <Card className="group overflow-hidden hover:shadow-lg transition-shadow duration-200">
      {/* Image */}
      <div className="relative aspect-square bg-gray-100 dark:bg-gray-700">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={product.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <PhotoIcon className="w-16 h-16 text-gray-300" />
          </div>
        )}
        
        {/* Overlay Actions */}
        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
          <button
            onClick={onEdit}
            className="p-2 bg-white dark:bg-zinc-900 rounded-full hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-700 transition-colors"
            title="Editar"
          >
            <PencilIcon className="w-5 h-5 text-gray-700 dark:text-zinc-300" />
          </button>
          <button
            onClick={onDuplicate}
            className="p-2 bg-white dark:bg-zinc-900 rounded-full hover:bg-gray-100 dark:hover:bg-zinc-700 dark:hover:bg-zinc-700 transition-colors"
            title="Duplicar"
          >
            <DocumentDuplicateIcon className="w-5 h-5 text-gray-700 dark:text-zinc-300" />
          </button>
          <button
            onClick={onDelete}
            className="p-2 bg-white dark:bg-zinc-900 rounded-full hover:bg-red-100 dark:bg-red-900/40 transition-colors"
            title="Excluir"
          >
            <TrashIcon className="w-5 h-5 text-red-600 dark:text-red-400" />
          </button>
        </div>

        {/* Featured Badge */}
        <button
          onClick={onToggleFeatured}
          className="absolute top-2 right-2 p-1.5 bg-white dark:bg-zinc-900 rounded-full shadow-sm hover:shadow-md transition-shadow"
          title={product.featured ? 'Remover destaque' : 'Destacar'}
        >
          {product.featured ? (
            <StarIconSolid className="w-5 h-5 text-yellow-500" />
          ) : (
            <StarIcon className="w-5 h-5 text-gray-400" />
          )}
        </button>

        {/* Sale Badge */}
        {product.is_on_sale && product.discount_percentage && (
          <div className="absolute top-2 left-2 bg-red-500 text-white text-xs font-bold px-2 py-1 rounded">
            -{product.discount_percentage}%
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Category & Type */}
        <div className="flex items-center gap-2 mb-2">
          {product.category_name && (
            <span className="text-xs text-gray-500 dark:text-zinc-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
              {product.category_name}
            </span>
          )}
          {product.product_type_name && (
            <span className="text-xs text-primary-600 bg-primary-50 px-2 py-0.5 rounded">
              {product.product_type_name}
            </span>
          )}
        </div>

        {/* Name */}
        <h3 className="font-semibold text-gray-900 dark:text-white mb-1 line-clamp-2">{product.name}</h3>
        
        {/* SKU */}
        <p className="text-xs text-gray-500 dark:text-zinc-400 mb-2">SKU: {product.sku}</p>

        {/* Price */}
        <div className="flex items-baseline gap-2 mb-3">
          <span className="text-lg font-bold text-primary-600">
            {formatMoney(product.price)}
          </span>
          {product.compare_at_price && product.compare_at_price > product.price && (
            <span className="text-sm text-gray-400 line-through">
              {formatMoney(product.compare_at_price)}
            </span>
          )}
        </div>

        {/* Stock & Status */}
        <div className="flex items-center justify-between">
          <StockBadge quantity={product.stock_quantity} threshold={product.low_stock_threshold} />
          <button
            onClick={onToggleStatus}
            className="text-xs text-gray-500 dark:text-zinc-400 hover:text-gray-700 dark:hover:text-zinc-300 dark:hover:text-zinc-300"
          >
            <StatusBadge status={product.status} />
          </button>
        </div>
      </div>
    </Card>
  );
};

// =============================================================================
// PRODUCT LIST ROW COMPONENT
// =============================================================================

interface ProductRowProps extends ProductCardProps {}

const ProductRow: React.FC<ProductRowProps> = ({
  product,
  onEdit,
  onDelete,
  onDuplicate,
  onToggleFeatured,
  onToggleStatus,
}) => {
  const imageUrl = product.main_image_url || product.main_image;
  
  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black transition-colors">
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-gray-100 dark:bg-gray-700 rounded-lg overflow-hidden flex-shrink-0">
            {imageUrl ? (
              <img src={imageUrl} alt={product.name} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <PhotoIcon className="w-6 h-6 text-gray-300" />
              </div>
            )}
          </div>
          <div>
            <p className="font-medium text-gray-900 dark:text-white">{product.name}</p>
            <p className="text-xs text-gray-500 dark:text-zinc-400">SKU: {product.sku}</p>
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-col gap-1">
          {product.category_name && (
            <span className="text-xs text-gray-600 dark:text-zinc-400">{product.category_name}</span>
          )}
          {product.product_type_name && (
            <span className="text-xs text-primary-600">{product.product_type_name}</span>
          )}
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-col">
          <span className="font-semibold text-gray-900 dark:text-white">{formatMoney(product.price)}</span>
          {product.compare_at_price && product.compare_at_price > product.price && (
            <span className="text-xs text-gray-400 line-through">
              {formatMoney(product.compare_at_price)}
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-3">
        <StockBadge quantity={product.stock_quantity} threshold={product.low_stock_threshold} />
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={product.status} />
      </td>
      <td className="px-4 py-3">
        <button onClick={onToggleFeatured}>
          {product.featured ? (
            <StarIconSolid className="w-5 h-5 text-yellow-500" />
          ) : (
            <StarIcon className="w-5 h-5 text-gray-300 hover:text-yellow-500" />
          )}
        </button>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1">
          <button
            onClick={onEdit}
            className="p-1.5 hover:bg-gray-100 dark:hover:bg-zinc-700 dark:bg-gray-700 rounded-lg transition-colors"
            title="Editar"
          >
            <PencilIcon className="w-4 h-4 text-gray-600 dark:text-zinc-400" />
          </button>
          <button
            onClick={onDuplicate}
            className="p-1.5 hover:bg-gray-100 dark:hover:bg-zinc-700 dark:bg-gray-700 rounded-lg transition-colors"
            title="Duplicar"
          >
            <DocumentDuplicateIcon className="w-4 h-4 text-gray-600 dark:text-zinc-400" />
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 hover:bg-red-50 rounded-lg transition-colors"
            title="Excluir"
          >
            <TrashIcon className="w-4 h-4 text-red-600 dark:text-red-400" />
          </button>
        </div>
      </td>
    </tr>
  );
};

// =============================================================================
// PRODUCT FORM MODAL
// =============================================================================

interface ProductFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  product?: Product | null;
  storeId: string;
  categories: Category[];
  productTypes: ProductType[];
  onSave: () => void;
}

const ProductFormModal: React.FC<ProductFormModalProps> = ({
  isOpen,
  onClose,
  product,
  storeId,
  categories,
  productTypes,
  onSave,
}) => {
  const isEditing = !!product;
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'basic' | 'pricing' | 'inventory' | 'media' | 'seo'>('basic');
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  
  const [formData, setFormData] = useState<ProductInput>({
    store: storeId,
    name: '',
    description: '',
    short_description: '',
    sku: '',
    barcode: '',
    price: 0,
    compare_at_price: undefined,
    cost_price: undefined,
    category: null,
    product_type: null,
    type_attributes: {},
    track_stock: true,
    stock_quantity: 0,
    low_stock_threshold: 5,
    allow_backorder: false,
    status: 'active',
    featured: false,
    tags: [],
    meta_title: '',
    meta_description: '',
  });

  // Selected product type for custom fields
  const selectedProductType = useMemo(() => {
    if (!formData.product_type) return null;
    return productTypes.find(pt => pt.id === formData.product_type) || null;
  }, [formData.product_type, productTypes]);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      if (product) {
        setFormData({
          store: storeId,
          name: product.name,
          description: product.description || '',
          short_description: product.short_description || '',
          sku: product.sku,
          barcode: product.barcode || '',
          price: product.price,
          compare_at_price: product.compare_at_price,
          cost_price: product.cost_price,
          category: product.category,
          product_type: product.product_type,
          type_attributes: product.type_attributes || {},
          track_stock: product.track_stock,
          stock_quantity: product.stock_quantity,
          low_stock_threshold: product.low_stock_threshold,
          allow_backorder: product.allow_backorder,
          status: product.status,
          featured: product.featured,
          tags: product.tags || [],
          meta_title: product.meta_title || '',
          meta_description: product.meta_description || '',
        });
        setImagePreview(product.main_image_url || product.main_image || null);
      } else {
        setFormData({
          store: storeId,
          name: '',
          description: '',
          short_description: '',
          sku: `SKU-${Date.now()}`,
          barcode: '',
          price: 0,
          compare_at_price: undefined,
          cost_price: undefined,
          category: null,
          product_type: null,
          type_attributes: {},
          track_stock: true,
          stock_quantity: 0,
          low_stock_threshold: 5,
          allow_backorder: false,
          status: 'active',
          featured: false,
          tags: [],
          meta_title: '',
          meta_description: '',
        });
        setImagePreview(null);
      }
      setActiveTab('basic');
    }
  }, [isOpen, product, storeId]);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setFormData(prev => ({ ...prev, main_image: file }));
      if (imagePreview?.startsWith('blob:')) {
        URL.revokeObjectURL(imagePreview);
      }
      setImagePreview(URL.createObjectURL(file));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.name.trim()) {
      toast.error('Nome é obrigatório');
      return;
    }
    if (formData.price <= 0) {
      toast.error('Preço deve ser maior que zero');
      return;
    }

    setSaving(true);
    try {
      if (isEditing && product) {
        await storesApi.updateProduct(product.id, formData);
        toast.success('Produto atualizado!');
      } else {
        await storesApi.createProduct(formData);
        toast.success('Produto criado!');
      }
      onSave();
      onClose();
    } catch (error) {
      logger.error('Error saving product:', error);
      toast.error('Erro ao salvar produto');
    } finally {
      setSaving(false);
    }
  };

  // Render custom field based on type
  const renderCustomField = (field: CustomField) => {
    const value = formData.type_attributes?.[field.name] ?? field.default_value ?? '';
    
    const updateField = (newValue: unknown) => {
      setFormData(prev => ({
        ...prev,
        type_attributes: {
          ...prev.type_attributes,
          [field.name]: newValue,
        },
      }));
    };

    switch (field.type) {
      case 'select':
        return (
          <select
            value={String(value)}
            onChange={(e) => updateField(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
            required={field.required}
          >
            <option value="">Selecione...</option>
            {field.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        );
      
      case 'multiselect':
        const selectedValues = Array.isArray(value) ? value : [];
        return (
          <div className="space-y-2">
            {field.options?.map((opt) => (
              <label key={opt.value} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selectedValues.includes(opt.value)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      updateField([...selectedValues, opt.value]);
                    } else {
                      updateField(selectedValues.filter((v: string) => v !== opt.value));
                    }
                  }}
                  className="rounded border-gray-300 dark:border-zinc-700 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm">{opt.label}</span>
              </label>
            ))}
          </div>
        );
      
      case 'boolean':
        return (
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => updateField(e.target.checked)}
              className="rounded border-gray-300 dark:border-zinc-700 text-primary-600 focus:ring-primary-500"
            />
            <span className="text-sm">{field.label}</span>
          </label>
        );
      
      case 'number':
        return (
          <input
            type="number"
            value={Number(value) || ''}
            onChange={(e) => updateField(Number(e.target.value))}
            min={field.min}
            max={field.max}
            step={field.step || 1}
            placeholder={field.placeholder}
            className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
            required={field.required}
          />
        );
      
      case 'textarea':
        return (
          <textarea
            value={String(value)}
            onChange={(e) => updateField(e.target.value)}
            rows={field.rows || 3}
            placeholder={field.placeholder}
            className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
            required={field.required}
          />
        );
      
      case 'color':
        return (
          <input
            type="color"
            value={String(value) || '#000000'}
            onChange={(e) => updateField(e.target.value)}
            className="w-full h-10 rounded-lg cursor-pointer"
          />
        );
      
      default:
        return (
          <input
            type="text"
            value={String(value)}
            onChange={(e) => updateField(e.target.value)}
            placeholder={field.placeholder}
            className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
            required={field.required}
          />
        );
    }
  };

  const tabs = [
    { id: 'basic', label: 'Básico', icon: CubeIcon },
    { id: 'pricing', label: 'Preços', icon: TagIcon },
    { id: 'inventory', label: 'Estoque', icon: CubeIcon },
    { id: 'media', label: 'Mídia', icon: PhotoIcon },
    { id: 'seo', label: 'SEO', icon: MagnifyingGlassIcon },
  ] as const;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Editar Produto' : 'Novo Produto'}
      size="xl"
    >
      <form onSubmit={handleSubmit}>
        {/* Tabs */}
        <div className="flex border-b border-gray-200 dark:border-zinc-800 mb-6 -mx-6 px-6">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === tab.id
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <div className="space-y-6 max-h-[60vh] overflow-y-auto px-1">
          {/* Basic Tab */}
          {activeTab === 'basic' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                  Nome do Produto *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                  placeholder="Ex: Rondelli 4 Queijos"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                    Categoria
                  </label>
                  <select
                    value={formData.category || ''}
                    onChange={(e) => setFormData(prev => ({ ...prev, category: e.target.value || null }))}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Sem categoria</option>
                    {categories.map((cat) => (
                      <option key={cat.id} value={cat.id}>{cat.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                    Tipo de Produto
                  </label>
                  <select
                    value={formData.product_type || ''}
                    onChange={(e) => setFormData(prev => ({ 
                      ...prev, 
                      product_type: e.target.value || null,
                      type_attributes: {}, // Reset attributes when type changes
                    }))}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="">Sem tipo</option>
                    {productTypes.map((pt) => (
                      <option key={pt.id} value={pt.id}>
                        {pt.icon} {pt.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Custom Fields from Product Type */}
              {selectedProductType && selectedProductType.custom_fields.length > 0 && (
                <div className="border-t pt-4 mt-4">
                  <h4 className="text-sm font-medium text-gray-700 dark:text-zinc-300 mb-3">
                    Campos de {selectedProductType.name}
                  </h4>
                  <div className="grid grid-cols-2 gap-4">
                    {selectedProductType.custom_fields.map((field) => (
                      <div key={field.name}>
                        <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                          {field.label} {field.required && '*'}
                        </label>
                        {renderCustomField(field)}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                  Descrição Curta
                </label>
                <input
                  type="text"
                  value={formData.short_description || ''}
                  onChange={(e) => setFormData(prev => ({ ...prev, short_description: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                  placeholder="Breve descrição para listagens"
                  maxLength={200}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                  Descrição Completa
                </label>
                <textarea
                  value={formData.description || ''}
                  onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                  placeholder="Descrição detalhada do produto..."
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                    SKU *
                  </label>
                  <input
                    type="text"
                    value={formData.sku || ''}
                    onChange={(e) => setFormData(prev => ({ ...prev, sku: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                    placeholder="Código único"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                    Código de Barras
                  </label>
                  <input
                    type="text"
                    value={formData.barcode || ''}
                    onChange={(e) => setFormData(prev => ({ ...prev, barcode: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                    placeholder="EAN/UPC"
                  />
                </div>
              </div>

              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={formData.featured}
                    onChange={(e) => setFormData(prev => ({ ...prev, featured: e.target.checked }))}
                    className="rounded border-gray-300 dark:border-zinc-700 text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-sm">Produto em destaque</span>
                </label>
              </div>
            </div>
          )}

          {/* Pricing Tab */}
          {activeTab === 'pricing' && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                    Preço de Venda *
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 dark:text-zinc-400">R$</span>
                    <input
                      type="number"
                      value={formData.price || ''}
                      onChange={(e) => setFormData(prev => ({ ...prev, price: Number(e.target.value) }))}
                      className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                      step="0.01"
                      min="0"
                      required
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                    Preço Comparativo
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 dark:text-zinc-400">R$</span>
                    <input
                      type="number"
                      value={formData.compare_at_price ?? ''}
                      onChange={(e) => setFormData(prev => ({
                        ...prev,
                        compare_at_price: e.target.value ? Number(e.target.value) : undefined,
                      }))}
                      className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                      step="0.01"
                      min="0"
                      placeholder="Preço original"
                    />
                  </div>
                  <p className="text-xs text-gray-500 dark:text-zinc-400 mt-1">Para mostrar desconto</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                    Custo
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 dark:text-zinc-400">R$</span>
                    <input
                      type="number"
                      value={formData.cost_price ?? ''}
                      onChange={(e) => setFormData(prev => ({
                        ...prev,
                        cost_price: e.target.value ? Number(e.target.value) : undefined,
                      }))}
                      className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                      step="0.01"
                      min="0"
                      placeholder="Custo do produto"
                    />
                  </div>
                  <p className="text-xs text-gray-500 dark:text-zinc-400 mt-1">Para cálculo de margem</p>
                </div>
              </div>

              {/* Margin Calculator */}
              {formData.price > 0 && formData.cost_price && formData.cost_price > 0 && (
                <Card className="p-4 bg-gray-50 dark:bg-black">
                  <h4 className="text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">Análise de Margem</h4>
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                      <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                        {formatMoney(formData.price - formData.cost_price)}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-zinc-400">Lucro Bruto</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                        {(((formData.price - formData.cost_price) / formData.price) * 100).toFixed(1)}%
                      </p>
                      <p className="text-xs text-gray-500 dark:text-zinc-400">Margem</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                        {(((formData.price - formData.cost_price) / formData.cost_price) * 100).toFixed(1)}%
                      </p>
                      <p className="text-xs text-gray-500 dark:text-zinc-400">Markup</p>
                    </div>
                  </div>
                </Card>
              )}
            </div>
          )}

          {/* Inventory Tab */}
          {activeTab === 'inventory' && (
            <div className="space-y-4">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.track_stock}
                  onChange={(e) => setFormData(prev => ({ ...prev, track_stock: e.target.checked }))}
                  className="rounded border-gray-300 dark:border-zinc-700 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm font-medium">Controlar estoque</span>
              </label>

              {formData.track_stock && (
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                      Quantidade em Estoque
                    </label>
                    <input
                      type="number"
                      value={formData.stock_quantity || 0}
                      onChange={(e) => setFormData(prev => ({ ...prev, stock_quantity: Number(e.target.value) }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                      min="0"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                      Alerta de Estoque Baixo
                    </label>
                    <input
                      type="number"
                      value={formData.low_stock_threshold || 5}
                      onChange={(e) => setFormData(prev => ({ ...prev, low_stock_threshold: Number(e.target.value) }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                      min="0"
                    />
                  </div>
                  <div className="flex items-end">
                    <label className="flex items-center gap-2 pb-2">
                      <input
                        type="checkbox"
                        checked={formData.allow_backorder}
                        onChange={(e) => setFormData(prev => ({ ...prev, allow_backorder: e.target.checked }))}
                        className="rounded border-gray-300 dark:border-zinc-700 text-primary-600 focus:ring-primary-500"
                      />
                      <span className="text-sm">Permitir venda sem estoque</span>
                    </label>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                  Status do Produto
                </label>
                <select
                  value={formData.status}
                  onChange={(e) => setFormData(prev => ({ ...prev, status: e.target.value as ProductInput['status'] }))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                >
                  <option value="active">Ativo</option>
                  <option value="inactive">Inativo</option>
                  <option value="out_of_stock">Sem Estoque</option>
                  <option value="discontinued">Descontinuado</option>
                </select>
              </div>
            </div>
          )}

          {/* Media Tab */}
          {activeTab === 'media' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">
                  Imagem Principal
                </label>
                <div className="flex items-start gap-4">
                  <div className="w-40 h-40 bg-gray-100 dark:bg-gray-700 rounded-lg overflow-hidden flex items-center justify-center border-2 border-dashed border-gray-300 dark:border-zinc-700">
                    {imagePreview ? (
                      <img src={imagePreview} alt="Preview" className="w-full h-full object-cover" />
                    ) : (
                      <PhotoIcon className="w-12 h-12 text-gray-400" />
                    )}
                  </div>
                  <div className="flex-1">
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleImageChange}
                      className="hidden"
                      id="product-image"
                    />
                    <label
                      htmlFor="product-image"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-white dark:bg-zinc-900 border border-gray-300 dark:border-zinc-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-zinc-700 dark:bg-black transition-colors"
                    >
                      <PhotoIcon className="w-5 h-5" />
                      Escolher Imagem
                    </label>
                    <p className="text-xs text-gray-500 dark:text-zinc-400 mt-2">
                      Recomendado: 800x800px, JPG ou PNG, máx 2MB
                    </p>
                    {imagePreview && (
                      <button
                        type="button"
                        onClick={() => {
                          setImagePreview(null);
                          setFormData(prev => ({ ...prev, main_image: null }));
                        }}
                        className="text-sm text-red-600 dark:text-red-400 hover:text-red-700 dark:text-red-300 mt-2"
                      >
                        Remover imagem
                      </button>
                    )}
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                  URL da Imagem (alternativo)
                </label>
                <input
                  type="url"
                  value={formData.main_image_url || ''}
                  onChange={(e) => setFormData(prev => ({ ...prev, main_image_url: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                  placeholder="https://exemplo.com/imagem.jpg"
                />
              </div>
            </div>
          )}

          {/* SEO Tab */}
          {activeTab === 'seo' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                  Título SEO
                </label>
                <input
                  type="text"
                  value={formData.meta_title || ''}
                  onChange={(e) => setFormData(prev => ({ ...prev, meta_title: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                  placeholder={formData.name || 'Título para mecanismos de busca'}
                  maxLength={60}
                />
                <p className="text-xs text-gray-500 dark:text-zinc-400 mt-1">
                  {(formData.meta_title || formData.name || '').length}/60 caracteres
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1">
                  Descrição SEO
                </label>
                <textarea
                  value={formData.meta_description || ''}
                  onChange={(e) => setFormData(prev => ({ ...prev, meta_description: e.target.value }))}
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
                  placeholder={formData.short_description || 'Descrição para mecanismos de busca'}
                  maxLength={160}
                />
                <p className="text-xs text-gray-500 dark:text-zinc-400 mt-1">
                  {(formData.meta_description || formData.short_description || '').length}/160 caracteres
                </p>
              </div>

              {/* SEO Preview */}
              <Card className="p-4 bg-gray-50 dark:bg-black">
                <h4 className="text-sm font-medium text-gray-700 dark:text-zinc-300 mb-2">Prévia no Google</h4>
                <div className="bg-white dark:bg-zinc-900 p-3 rounded border">
                  <p className="text-blue-600 dark:text-blue-400 text-lg hover:underline cursor-pointer">
                    {formData.meta_title || formData.name || 'Título do Produto'}
                  </p>
                  <p className="text-green-700 dark:text-green-300 text-sm">
                    sualoja.com.br › produtos › {formData.sku || 'sku'}
                  </p>
                  <p className="text-gray-600 dark:text-zinc-400 text-sm line-clamp-2">
                    {formData.meta_description || formData.short_description || formData.description || 'Descrição do produto aparecerá aqui...'}
                  </p>
                </div>
              </Card>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" isLoading={saving}>
            {isEditing ? 'Salvar Alterações' : 'Criar Produto'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};

// =============================================================================
// MAIN PAGE COMPONENT
// =============================================================================

export const ProductsPageNew: React.FC = () => {
  const navigate = useNavigate();
  const { storeId: routeStoreId } = useParams<{ storeId?: string }>();
  const { storeId: contextStoreId, storeName, isStoreSelected } = useStore();
  
  const storeId = routeStoreId || contextStoreId;

  // State
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [productTypes, setProductTypes] = useState<ProductType[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  
  // Filters
  const [search, setSearch] = useState('');
  const [filterCategory, setFilterCategory] = useState<string>('');
  const [filterType, setFilterType] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [showFilters, setShowFilters] = useState(false);

  // Modal state
  const [isFormModalOpen, setIsFormModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [deletingProduct, setDeletingProduct] = useState<Product | null>(null);

  // Load data
  const loadData = useCallback(async () => {
    if (!storeId) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const [productsRes, categoriesRes, typesRes] = await Promise.all([
        storesApi.getProducts({
          store: storeId,
          search: search || undefined,
          category: filterCategory || undefined,
          product_type: filterType || undefined,
          status: filterStatus || undefined,
          page_size: 100,
        }),
        storesApi.getCategories(storeId),
        storesApi.getProductTypes(storeId),
      ]);
      
      setProducts(productsRes.results);
      setCategories(categoriesRes.results || []);
      setProductTypes(typesRes.results || []);
    } catch (error) {
      logger.error('Error loading products:', error);
      toast.error('Erro ao carregar produtos');
    } finally {
      setLoading(false);
    }
  }, [storeId, search, filterCategory, filterType, filterStatus]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handlers
  const handleEdit = (product: Product) => {
    setEditingProduct(product);
    setIsFormModalOpen(true);
  };

  const handleCreate = () => {
    setEditingProduct(null);
    setIsFormModalOpen(true);
  };

  const handleDelete = async () => {
    if (!deletingProduct) return;
    
    try {
      await storesApi.deleteProduct(deletingProduct.id);
      toast.success('Produto excluído!');
      setDeletingProduct(null);
      loadData();
    } catch (error) {
      logger.error('Error deleting product:', error);
      toast.error('Erro ao excluir produto');
    }
  };

  const handleDuplicate = async (product: Product) => {
    try {
      await storesApi.duplicateProduct(product.id);
      toast.success('Produto duplicado!');
      loadData();
    } catch (error) {
      logger.error('Error duplicating product:', error);
      toast.error('Erro ao duplicar produto');
    }
  };

  const handleToggleFeatured = async (product: Product) => {
    try {
      await storesApi.updateProduct(product.id, { featured: !product.featured });
      loadData();
    } catch (error) {
      logger.error('Error toggling featured:', error);
    }
  };

  const handleToggleStatus = async (product: Product) => {
    try {
      const nextStatus = product.status === 'active' ? 'inactive' : 'active';
      await storesApi.updateProduct(product.id, { status: nextStatus });
      loadData();
    } catch (error) {
      logger.error('Error toggling status:', error);
    }
  };

  // Stats
  const stats = useMemo(() => {
    const total = products.length;
    const active = products.filter(p => p.status === 'active').length;
    const lowStock = products.filter(p => p.stock_quantity <= (p.low_stock_threshold || 5) && p.stock_quantity > 0).length;
    const outOfStock = products.filter(p => p.stock_quantity <= 0).length;
    const featured = products.filter(p => p.featured).length;
    return { total, active, lowStock, outOfStock, featured };
  }, [products]);

  if (!storeId) {
    return (
      <div className="p-6 text-center">
        <ExclamationTriangleIcon className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Nenhuma loja selecionada</h2>
        <p className="text-gray-500 dark:text-zinc-400 mb-4">Selecione uma loja no menu superior para gerenciar produtos.</p>
        <Button onClick={() => navigate('/stores')}>
          Ver Lojas
        </Button>
      </div>
    );
  }

  if (loading && products.length === 0) {
    return <Loading />;
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Produtos</h1>
          <p className="text-gray-500 dark:text-zinc-400">
            {storeName ? `Catálogo de ${storeName}` : 'Gerencie seu catálogo de produtos'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={loadData} title="Atualizar">
            <ArrowPathIcon className="w-5 h-5" />
          </Button>
          <Button onClick={handleCreate}>
            <PlusIcon className="w-5 h-5 mr-2" />
            Novo Produto
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="p-4 text-center">
          <p className="text-3xl font-bold text-gray-900 dark:text-white">{stats.total}</p>
          <p className="text-sm text-gray-500 dark:text-zinc-400">Total</p>
        </Card>
        <Card className="p-4 text-center">
          <p className="text-3xl font-bold text-green-600 dark:text-green-400">{stats.active}</p>
          <p className="text-sm text-gray-500 dark:text-zinc-400">Ativos</p>
        </Card>
        <Card className="p-4 text-center">
          <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">{stats.lowStock}</p>
          <p className="text-sm text-gray-500 dark:text-zinc-400">Estoque Baixo</p>
        </Card>
        <Card className="p-4 text-center">
          <p className="text-3xl font-bold text-red-600 dark:text-red-400">{stats.outOfStock}</p>
          <p className="text-sm text-gray-500 dark:text-zinc-400">Sem Estoque</p>
        </Card>
        <Card className="p-4 text-center">
          <p className="text-3xl font-bold text-purple-600 dark:text-purple-400">{stats.featured}</p>
          <p className="text-sm text-gray-500 dark:text-zinc-400">Destaques</p>
        </Card>
      </div>

      {/* Filters */}
      <Card className="p-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Search */}
          <div className="flex-1 relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nome, SKU..."
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500"
            />
          </div>

          {/* Filter Dropdowns */}
          <div className="flex flex-wrap gap-2">
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
            >
              <option value="">Todas Categorias</option>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>{cat.name}</option>
              ))}
            </select>

            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
            >
              <option value="">Todos Tipos</option>
              {productTypes.map((pt) => (
                <option key={pt.id} value={pt.id}>{pt.icon} {pt.name}</option>
              ))}
            </select>

            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
            >
              <option value="">Todos Status</option>
              <option value="active">Ativos</option>
              <option value="inactive">Inativos</option>
              <option value="out_of_stock">Sem Estoque</option>
              <option value="discontinued">Descontinuados</option>
            </select>

            {/* View Mode Toggle */}
            <div className="flex items-center bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1.5 rounded ${viewMode === 'grid' ? 'bg-white dark:bg-gray-700 shadow-sm' : 'text-gray-500 dark:text-zinc-400'}`}
              >
                <Squares2X2Icon className="w-5 h-5" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded ${viewMode === 'list' ? 'bg-white dark:bg-gray-700 shadow-sm' : 'text-gray-500 dark:text-zinc-400'}`}
              >
                <ListBulletIcon className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </Card>

      {/* Products Grid/List */}
      {products.length === 0 ? (
        <Card className="p-12 text-center">
          <CubeIcon className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Nenhum produto encontrado</h3>
          <p className="text-gray-500 dark:text-zinc-400 mb-4">
            {search || filterCategory || filterType || filterStatus
              ? 'Tente ajustar os filtros'
              : 'Comece adicionando seu primeiro produto'}
          </p>
          <Button onClick={handleCreate}>
            <PlusIcon className="w-5 h-5 mr-2" />
            Adicionar Produto
          </Button>
        </Card>
      ) : viewMode === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {products.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              onEdit={() => handleEdit(product)}
              onDelete={() => setDeletingProduct(product)}
              onDuplicate={() => handleDuplicate(product)}
              onToggleFeatured={() => handleToggleFeatured(product)}
              onToggleStatus={() => handleToggleStatus(product)}
            />
          ))}
        </div>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-black border-b">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">Produto</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">Categoria/Tipo</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">Preço</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">Estoque</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">Destaque</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-zinc-400 uppercase">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {products.map((product) => (
                <ProductRow
                  key={product.id}
                  product={product}
                  onEdit={() => handleEdit(product)}
                  onDelete={() => setDeletingProduct(product)}
                  onDuplicate={() => handleDuplicate(product)}
                  onToggleFeatured={() => handleToggleFeatured(product)}
                  onToggleStatus={() => handleToggleStatus(product)}
                />
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Product Form Modal */}
      <ProductFormModal
        isOpen={isFormModalOpen}
        onClose={() => {
          setIsFormModalOpen(false);
          setEditingProduct(null);
        }}
        product={editingProduct}
        storeId={storeId}
        categories={categories}
        productTypes={productTypes}
        onSave={loadData}
      />

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deletingProduct}
        onClose={() => setDeletingProduct(null)}
        title="Excluir Produto"
      >
        <div className="space-y-4">
          <p className="text-gray-600 dark:text-zinc-400">
            Tem certeza que deseja excluir o produto <strong>{deletingProduct?.name}</strong>?
          </p>
          <p className="text-sm text-red-600 dark:text-red-400">
            Esta ação não pode ser desfeita.
          </p>
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setDeletingProduct(null)}>
              Cancelar
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              Excluir
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ProductsPageNew;
