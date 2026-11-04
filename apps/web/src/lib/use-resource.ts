"use client";

import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

type Resource<T> = {
  data: T | null;
  error: string | null;
  setData: Dispatch<SetStateAction<T | null>>;
};

/**
 * Carga un recurso de la API y, mientras `shouldPoll(data)` sea verdadero, lo vuelve a pedir
 * cada `pollMs`. `fetcher` debe ser estable (useCallback) para no recargar en cada render.
 */
export function useResource<T>(
  fetcher: () => Promise<T>,
  shouldPoll: (data: T | null) => boolean = () => false,
  pollMs = 3000,
): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let ignore = false;
    fetcher().then(
      (result) => {
        if (ignore) return;
        setData(result);
        setError(null);
      },
      (e: unknown) => {
        if (!ignore) setError(e instanceof Error ? e.message : "Error al cargar.");
      },
    );
    return () => {
      ignore = true;
    };
  }, [fetcher, tick]);

  const polling = shouldPoll(data);
  useEffect(() => {
    if (!polling) return;
    const t = setInterval(() => setTick((n) => n + 1), pollMs);
    return () => clearInterval(t);
  }, [polling, pollMs]);

  return { data, error, setData };
}
