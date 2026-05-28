import { useCallback, useEffect, useMemo, useState } from "react";
import type { AccountsUpdatePayload, ConfigResponse, ExecConfigMeta, SessionConfig, WebhookEntry } from "@/execution/lib/types";

export function useConfig(
  subscribe?: (type: string, cb: (data: unknown) => void) => () => void,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    if (!enabled) return;
    try {
      const r = await fetch("/exec-api/config");
      if (!r.ok) return;
      const data: ConfigResponse = await r.json();
      setConfig(data);
    } catch {
      // ignore fetch errors
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    fetchConfig().finally(() => setLoading(false));
  }, [enabled, fetchConfig]);

  // React to accounts_update WebSocket messages to keep execConfigs in sync
  useEffect(() => {
    if (!enabled || !subscribe) return;
    return subscribe("accounts_update", (data) => {
      const payload = data as AccountsUpdatePayload;
      setConfig((prev) => {
        if (!prev?.exec_configs) return prev;
        const ec = prev.exec_configs[payload.exec_config];
        if (!ec) return prev;
        return {
          ...prev,
          exec_configs: {
            ...prev.exec_configs,
            [payload.exec_config]: { ...ec, webhooks: payload.webhooks },
          },
        };
      });
    });
  }, [enabled, subscribe]);

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

  const updateWebhooks = useCallback(
    async (configName: string, webhooks: WebhookEntry[]) => {
      setSaving(true);
      setError(null);
      try {
        const r = await fetch(`/exec-api/config/exec/${configName}/webhooks`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ webhooks }),
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
        const msg = e instanceof Error ? e.message : "Failed to save webhooks";
        setError(msg);
        throw e;
      } finally {
        setSaving(false);
      }
    },
    [fetchConfig],
  );

  const pauseWebhook = useCallback(
    async (configName: string, idx: number) => {
      setSaving(true);
      setError(null);
      try {
        const r = await fetch(`/exec-api/config/exec/${configName}/webhooks/${idx}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paused: true }),
        });
        if (!r.ok) {
          const err = await r.json();
          throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
        }
        await fetchConfig();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to pause");
        throw e;
      } finally {
        setSaving(false);
      }
    },
    [fetchConfig],
  );

  const resumeWebhook = useCallback(
    async (configName: string, idx: number) => {
      setSaving(true);
      setError(null);
      try {
        const r = await fetch(`/exec-api/config/exec/${configName}/webhooks/${idx}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paused: false }),
        });
        if (!r.ok) {
          const err = await r.json();
          throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
        }
        await fetchConfig();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to resume");
        throw e;
      } finally {
        setSaving(false);
      }
    },
    [fetchConfig],
  );

  const updateWebhookMultiplier = useCallback(
    async (configName: string, idx: number, multiplier: number) => {
      setSaving(true);
      setError(null);
      try {
        const r = await fetch(`/exec-api/config/exec/${configName}/webhooks/${idx}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ multiplier }),
        });
        if (!r.ok) {
          const err = await r.json();
          throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
        }
        await fetchConfig();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to update multiplier");
        throw e;
      } finally {
        setSaving(false);
      }
    },
    [fetchConfig],
  );

  const flattenWebhook = useCallback(
    async (configName: string, idx: number) => {
      setSaving(true);
      setError(null);
      try {
        const r = await fetch(`/exec-api/config/exec/${configName}/webhooks/${idx}/flatten`, {
          method: "POST",
        });
        if (!r.ok) {
          const err = await r.json();
          throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to flatten");
        throw e;
      } finally {
        setSaving(false);
      }
    },
    [],
  );

  const pauseEngine = useCallback(
    async (sessionName: string, configName?: string) => {
      const params = configName ? `?config=${encodeURIComponent(configName)}` : "";
      const r = await fetch(`/exec-api/engines/${sessionName}/pause${params}`, {
        method: "POST",
      });
      if (!r.ok) {
        const err = await r.json();
        throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      }
    },
    [],
  );

  const resumeEngine = useCallback(
    async (sessionName: string, configName?: string) => {
      const params = configName ? `?config=${encodeURIComponent(configName)}` : "";
      const r = await fetch(`/exec-api/engines/${sessionName}/resume${params}`, {
        method: "POST",
      });
      if (!r.ok) {
        const err = await r.json();
        throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      }
    },
    [],
  );

  const toggleEnabled = useCallback(
    async (configName: string, enabled: boolean) => {
      setSaving(true);
      setError(null);
      try {
        const r = await fetch(`/exec-api/config/exec/${configName}/enabled`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled }),
        });
        if (!r.ok) {
          const err = await r.json();
          throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
        }
        await fetchConfig();
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to toggle enabled";
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

  return {
    config, loading, saving, error,
    updateSession, resetSession, updateWebhooks, execConfigs,
    pauseWebhook, resumeWebhook, updateWebhookMultiplier, flattenWebhook,
    pauseEngine, resumeEngine, toggleEnabled,
  };
}
