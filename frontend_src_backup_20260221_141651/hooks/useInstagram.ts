// @ts-nocheck
import { useState, useCallback, useEffect } from 'react';
import { instagramService, InstagramAccount, InstagramMedia, InstagramStory, InstagramReel, InstagramCatalog, InstagramProduct, InstagramLive } from '../services/instagram';
import toast from 'react-hot-toast';

// ============================================
// ACCOUNTS
// ============================================

export const useInstagramAccounts = () => {
  const [accounts, setAccounts] = useState<InstagramAccount[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchAccounts = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await instagramService.getAccounts();
      setAccounts(res.data?.results || []);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  return { accounts, isLoading, error, refetch: fetchAccounts };
};

export const useInstagramAccount = (id: string) => {
  const [account, setAccount] = useState<InstagramAccount | null>(null);
  const [isLoading, setIsLoading] = useState(!!id);

  const fetchAccount = useCallback(async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const res = await instagramService.getAccount(id);
      setAccount(res.data);
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchAccount();
  }, [fetchAccount]);

  return { account, isLoading, refetch: fetchAccount };
};

// ============================================
// MEDIA (POSTS)
// ============================================

export const useInstagramMedia = (accountId: string) => {
  const [media, setMedia] = useState<InstagramMedia[]>([]);
  const [isLoading, setIsLoading] = useState(!!accountId);

  const fetchMedia = useCallback(async () => {
    if (!accountId) return;
    setIsLoading(true);
    try {
      const res = await instagramService.getMedia(accountId);
      setMedia(res.data?.results || []);
    } finally {
      setIsLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    fetchMedia();
  }, [fetchMedia]);

  const createPost = useCallback(async (data: { caption?: string; media_urls: string[]; tags?: string[] }) => {
    try {
      const res = await instagramService.createPost({ account: accountId, ...data });
      await fetchMedia();
      toast.success('Post criado!');
      return res.data;
    } catch (err) {
      toast.error('Erro ao criar post');
      throw err;
    }
  }, [accountId, fetchMedia]);

  const createCarousel = useCallback(async (data: { caption?: string; media_urls: string[]; tags?: string[] }) => {
    try {
      const res = await instagramService.createCarousel({ account: accountId, ...data });
      await fetchMedia();
      toast.success('Carrossel criado!');
      return res.data;
    } catch (err) {
      toast.error('Erro ao criar carrossel');
      throw err;
    }
  }, [accountId, fetchMedia]);

  return { media, isLoading, refetch: fetchMedia, createPost, createCarousel };
};

// ============================================
// STORIES
// ============================================

export const useInstagramStories = (accountId: string) => {
  const [stories, setStories] = useState<InstagramStory[]>([]);
  const [isLoading, setIsLoading] = useState(!!accountId);

  const fetchStories = useCallback(async () => {
    if (!accountId) return;
    setIsLoading(true);
    try {
      const res = await instagramService.getStories(accountId);
      setStories(res.data?.results || []);
    } finally {
      setIsLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    fetchStories();
  }, [fetchStories]);

  const createStory = useCallback(async (data: { media_url: string; caption?: string }) => {
    try {
      const res = await instagramService.createStory({ account: accountId, ...data });
      await fetchStories();
      toast.success('Story criado!');
      return res.data;
    } catch (err) {
      toast.error('Erro ao criar story');
      throw err;
    }
  }, [accountId, fetchStories]);

  return { stories, isLoading, refetch: fetchStories, createStory };
};

// ============================================
// REELS
// ============================================

export const useInstagramReels = (accountId: string) => {
  const [reels, setReels] = useState<InstagramReel[]>([]);
  const [isLoading, setIsLoading] = useState(!!accountId);

  const fetchReels = useCallback(async () => {
    if (!accountId) return;
    setIsLoading(true);
    try {
      const res = await instagramService.getReels(accountId);
      setReels(res.data?.results || []);
    } finally {
      setIsLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    fetchReels();
  }, [fetchReels]);

  const createReel = useCallback(async (data: { video_url: string; caption?: string; cover_url?: string }) => {
    try {
      const res = await instagramService.createReel({ account: accountId, ...data });
      await fetchReels();
      toast.success('Reel criado!');
      return res.data;
    } catch (err) {
      toast.error('Erro ao criar reel');
      throw err;
    }
  }, [accountId, fetchReels]);

  return { reels, isLoading, refetch: fetchReels, createReel };
};

// ============================================
// SHOPPING - CATALOGS
// ============================================

export const useInstagramCatalogs = (accountId: string) => {
  const [catalogs, setCatalogs] = useState<InstagramCatalog[]>([]);
  const [isLoading, setIsLoading] = useState(!!accountId);

  const fetchCatalogs = useCallback(async () => {
    if (!accountId) return;
    setIsLoading(true);
    try {
      const res = await instagramService.getCatalogs(accountId);
      setCatalogs(res.data?.results || []);
    } finally {
      setIsLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    fetchCatalogs();
  }, [fetchCatalogs]);

  return { catalogs, isLoading, refetch: fetchCatalogs };
};

// ============================================
// SHOPPING - PRODUCTS
// ============================================

export const useInstagramProducts = (catalogId: string) => {
  const [products, setProducts] = useState<InstagramProduct[]>([]);
  const [isLoading, setIsLoading] = useState(!!catalogId);

  const fetchProducts = useCallback(async () => {
    if (!catalogId) return;
    setIsLoading(true);
    try {
      const res = await instagramService.getProducts(catalogId);
      setProducts(res.data?.results || []);
    } finally {
      setIsLoading(false);
    }
  }, [catalogId]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  const createProduct = useCallback(async (data: { name: string; price: number; currency: string; image_url: string; description?: string }) => {
    try {
      const res = await instagramService.createProduct({ catalog: catalogId, ...data });
      await fetchProducts();
      toast.success('Produto criado!');
      return res.data;
    } catch (err) {
      toast.error('Erro ao criar produto');
      throw err;
    }
  }, [catalogId, fetchProducts]);

  return { products, isLoading, refetch: fetchProducts, createProduct };
};

// ============================================
// LIVE
// ============================================

export const useInstagramLives = (accountId: string) => {
  const [lives, setLives] = useState<InstagramLive[]>([]);
  const [isLoading, setIsLoading] = useState(!!accountId);

  const fetchLives = useCallback(async () => {
    if (!accountId) return;
    setIsLoading(true);
    try {
      const res = await instagramService.getLives(accountId);
      setLives(res.data?.results || []);
    } finally {
      setIsLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    fetchLives();
  }, [fetchLives]);

  const createLive = useCallback(async (data: { title?: string; description?: string; scheduled_start?: string }) => {
    try {
      const res = await instagramService.createLive({ account: accountId, ...data });
      await fetchLives();
      toast.success('Live criada!');
      return res.data;
    } catch (err) {
      toast.error('Erro ao criar live');
      throw err;
    }
  }, [accountId, fetchLives]);

  return { lives, isLoading, refetch: fetchLives, createLive };
};

export default {
  useInstagramAccounts,
  useInstagramMedia,
  useInstagramStories,
  useInstagramReels,
};
