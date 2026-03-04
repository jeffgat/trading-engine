import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  SessionStatus,
  StatusResponse,
} from "@/execution/lib/types";

export function useStatus(
  subscribe: (type: string, cb: (data: unknown) => void) => () => void,
) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  // Track the server-reported uptime and when we received it
  const serverUptimeRef = useRef<{ value: number; receivedAt: number }>({
    value: 0,
    receivedAt: Date.now(),
  });
  const [uptime, setUptime] = useState(0);

  // Initial fetch
  useEffect(() => {
    fetch("/exec-api/status")
      .then((r) => r.json())
      .then((data: StatusResponse) => {
        serverUptimeRef.current = {
          value: data.uptime_seconds,
          receivedAt: Date.now(),
        };
        setUptime(data.uptime_seconds);
        setStatus(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // WebSocket updates
  const handleUpdate = useCallback((data: unknown) => {
    const d = data as StatusResponse;
    serverUptimeRef.current = {
      value: d.uptime_seconds,
      receivedAt: Date.now(),
    };
    setUptime(d.uptime_seconds);
    setStatus(d);
  }, []);

  useEffect(() => {
    return subscribe("status", handleUpdate);
  }, [subscribe, handleUpdate]);

  // Tick uptime locally every second
  useEffect(() => {
    const id = setInterval(() => {
      const { value, receivedAt } = serverUptimeRef.current;
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

  return { status, uptime, loading, configEngines, engines };
}
