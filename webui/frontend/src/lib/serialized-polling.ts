"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface SerializedPollingOptions<T> {
  enabled: boolean;
  poll: () => Promise<T>;
  intervalMs: number;
  resetKey?: string | null;
  initialValue?: T | null;
  errorMessage: (reason: unknown) => string;
}

interface SerializedPollingResult<T> {
  value: T | null;
  pollingError: string | null;
  refresh: () => Promise<void>;
  acceptActionValue: (value: T) => void;
}

export function useSerializedPolling<T>({
  enabled,
  poll,
  intervalMs,
  resetKey,
  initialValue = null,
  errorMessage,
}: SerializedPollingOptions<T>): SerializedPollingResult<T> {
  const [value, setValue] = useState<T | null>(initialValue);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const pollRef = useRef(poll);
  const errorMessageRef = useRef(errorMessage);
  const inFlightRef = useRef<Promise<void> | null>(null);
  const revisionRef = useRef(0);
  const mountedRef = useRef(true);

  pollRef.current = poll;
  errorMessageRef.current = errorMessage;

  const refresh = useCallback((): Promise<void> => {
    if (!enabled) return Promise.resolve();
    if (inFlightRef.current) return inFlightRef.current;

    const revision = revisionRef.current;
    const request = pollRef.current()
      .then((nextValue) => {
        if (!mountedRef.current || revision !== revisionRef.current) return;
        setValue(nextValue);
        setPollingError(null);
      })
      .catch((reason: unknown) => {
        if (!mountedRef.current || revision !== revisionRef.current) return;
        setPollingError(errorMessageRef.current(reason));
      })
      .finally(() => {
        if (inFlightRef.current === request) inFlightRef.current = null;
      });
    inFlightRef.current = request;
    return request;
  }, [enabled]);

  const acceptActionValue = useCallback((nextValue: T) => {
    revisionRef.current += 1;
    setValue(nextValue);
  }, []);

  useEffect(() => {
    revisionRef.current += 1;
    inFlightRef.current = null;
    setValue(initialValue);
    setPollingError(null);
  }, [initialValue, resetKey]);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) return () => { mountedRef.current = false; };
    void refresh();
    const timer = window.setInterval(() => void refresh(), intervalMs);
    return () => {
      mountedRef.current = false;
      window.clearInterval(timer);
    };
  }, [enabled, intervalMs, refresh, resetKey]);

  return { value, pollingError, refresh, acceptActionValue };
}
