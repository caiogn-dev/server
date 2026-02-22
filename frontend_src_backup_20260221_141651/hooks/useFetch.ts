import { useCallback, useEffect, useState } from 'react';

export interface UseFetchResult<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  refresh: () => Promise<void>;
}

export const useFetch = <T>(fetcher: () => Promise<T>): UseFetchResult<T> => {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const execute = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetcher();
      setData(response);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    execute();
  }, [execute]);

  return { data, loading, error, refresh: execute };
};
