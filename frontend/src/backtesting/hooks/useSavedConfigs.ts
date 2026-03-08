import { useCallback, useEffect, useState } from "react";
import type { SavedConfig } from "@/backtesting/lib/types";

export type SavedConfigInput = Omit<SavedConfig, "id" | "timestamp" | "updated_at">;

interface UseSavedConfigsReturn {
  configs: SavedConfig[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  loadConfig: (id: number) => Promise<SavedConfig | null>;
  createConfig: (payload: SavedConfigInput) => Promise<SavedConfig | null>;
  updateConfig: (id: number, payload: SavedConfigInput) => Promise<SavedConfig | null>;
  deleteConfig: (id: number) => Promise<boolean>;
}

export function useSavedConfigs(): UseSavedConfigsReturn {
  const [configs, setConfigs] = useState<SavedConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/bt-api/configs");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setConfigs(json.result ?? json);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load configs";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadConfig = useCallback(async (id: number): Promise<SavedConfig | null> => {
    try {
      const res = await fetch(`/bt-api/configs/${id}`);
      if (!res.ok) return null;
      const json = await res.json();
      return json.result ?? json;
    } catch {
      return null;
    }
  }, []);

  const createConfig = useCallback(async (payload: SavedConfigInput): Promise<SavedConfig | null> => {
    try {
      const res = await fetch("/bt-api/configs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) return null;
      const json = await res.json();
      const result: SavedConfig = json.result ?? json;
      await refresh();
      return result;
    } catch {
      return null;
    }
  }, [refresh]);

  const updateConfig = useCallback(async (id: number, payload: SavedConfigInput): Promise<SavedConfig | null> => {
    try {
      const res = await fetch(`/bt-api/configs/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) return null;
      const json = await res.json();
      const result: SavedConfig = json.result ?? json;
      await refresh();
      return result;
    } catch {
      return null;
    }
  }, [refresh]);

  const deleteConfig = useCallback(async (id: number): Promise<boolean> => {
    try {
      const res = await fetch(`/bt-api/configs/${id}`, { method: "DELETE" });
      if (!res.ok) return false;
      await refresh();
      return true;
    } catch {
      return false;
    }
  }, [refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { configs, loading, error, refresh, loadConfig, createConfig, updateConfig, deleteConfig };
}
