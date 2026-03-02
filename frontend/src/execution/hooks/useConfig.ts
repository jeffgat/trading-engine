import { useCallback, useEffect, useMemo, useState } from "react";
import type { ConfigResponse, ExecConfigMeta, SessionConfig } from "@/execution/lib/types";

export function useConfig() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    try {
      const r = await fetch("/exec-api/config");
      const data: ConfigResponse = await r.json();
      setConfig(data);
    } catch {
      // ignore fetch errors
    }
  }, []);

  useEffect(() => {
    fetchConfig().finally(() => setLoading(false));
  }, [fetchConfig]);

  const updateSession = useCallback(
    async (sessionName: string, overrides: Partial<SessionConfig>) => {
      setSaving(true);
      setError(null);
      try {
        const r = await fetch(`/exec-api/config/sessions/${sessionName}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ overrides }),
        });
        if (!r.ok) {
          const err = await r.json();
          const msg =
            typeof err.detail === "string"
              ? err.detail
              : Array.isArray(err.detail)
                ? err.detail.join("; ")
                : JSON.stringify(err.detail);
          throw new Error(msg);
        }
        await fetchConfig();
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to save";
        setError(msg);
        throw e;
      } finally {
        setSaving(false);
      }
    },
    [fetchConfig],
  );

  const resetSession = useCallback(
    async (sessionName: string) => {
      setSaving(true);
      setError(null);
      try {
        const r = await fetch(`/exec-api/config/sessions/${sessionName}`, {
          method: "DELETE",
        });
        if (!r.ok) {
          const err = await r.json();
          const msg =
            typeof err.detail === "string"
              ? err.detail
              : JSON.stringify(err.detail);
          throw new Error(msg);
        }
        await fetchConfig();
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to reset";
        setError(msg);
        throw e;
      } finally {
        setSaving(false);
      }
    },
    [fetchConfig],
  );

  const execConfigs: Record<string, ExecConfigMeta> = useMemo(() => {
    return config?.exec_configs ?? {};
  }, [config]);

  return { config, loading, saving, error, updateSession, resetSession, execConfigs };
}
