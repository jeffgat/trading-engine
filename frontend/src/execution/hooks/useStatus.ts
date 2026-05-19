import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  SessionStatus,
  StatusResponse,
} from "@/execution/lib/types";

export function useStatus(
  subscribe: (type: string, cb: (data: unknown) => void) => () => void,
  streamConnected = false,
) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [pollingHealthy, setPollingHealthy] = useState(false);
  // Track the server-reported uptime and when we received it
  const serverUptimeRef = useRef<{ value: number; receivedAt: number }>({
    value: 0,
    receivedAt: 0,
  });
  const [uptime, setUptime] = useState(0);

  const applyStatus = useCallback((data: StatusResponse) => {
    serverUptimeRef.current = {
      value: data.uptime_seconds,
      receivedAt: Date.now(),
    };
    setUptime(data.uptime_seconds);
    setStatus(data);
  }, []);

  const fetchStatus = useCallback(async () => {
    const response = await fetch("/exec-api/status");
    if (!response.ok) throw new Error(`Status request failed: ${response.status}`);
    return (await response.json()) as StatusResponse;
  }, []);

  // Initial fetch
  useEffect(() => {
    let cancelled = false;

    fetchStatus()
      .then((data) => {
        if (cancelled) return;
        applyStatus(data);
        setPollingHealthy(true);
      })
      .catch(() => {
        if (!cancelled) setPollingHealthy(false);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [applyStatus, fetchStatus]);

  // Keep REST polling alive while the WebSocket stream is unavailable.
  useEffect(() => {
    if (streamConnected) return;
    const id = setInterval(() => {
      fetchStatus()
        .then((data) => {
          applyStatus(data);
          setPollingHealthy(true);
        })
        .catch(() => setPollingHealthy(false));
    }, 10_000);
    return () => clearInterval(id);
  }, [applyStatus, fetchStatus, streamConnected]);

  // WebSocket updates
  const handleUpdate = useCallback((data: unknown) => {
    applyStatus(data as StatusResponse);
  }, [applyStatus]);

  useEffect(() => {
    return subscribe("status", handleUpdate);
  }, [subscribe, handleUpdate]);

  // Tick uptime locally every second
  useEffect(() => {
    const id = setInterval(() => {
      const { value, receivedAt } = serverUptimeRef.current;
      if (receivedAt === 0) return;
      const elapsed = Math.floor((Date.now() - receivedAt) / 1000);
      setUptime(value + elapsed);
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // Derive config-grouped engines and flat engines list
  const configEngines: Record<string, SessionStatus[]> = useMemo(() => {
    if (!status?.configs) return {};
    const result: Record<string, SessionStatus[]> = {};
    for (const [configName, group] of Object.entries(status.configs)) {
      result[configName] = (group.engines ?? []).map((e) => ({
        ...e,
        config_name: e.config_name ?? configName,
      }));
    }
    return result;
  }, [status]);

  const engines: SessionStatus[] = useMemo(() => {
    return Object.values(configEngines).flat();
  }, [configEngines]);

  return {
    status,
    uptime,
    loading,
    pollingHealthy: pollingHealthy && !streamConnected,
    configEngines,
    engines,
  };
}
