import { useCallback, useEffect, useState } from "react";
import type { StatusResponse } from "@/lib/types";

export function useStatus(
  subscribe: (type: string, cb: (data: unknown) => void) => () => void,
) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Initial fetch
  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((data: StatusResponse) => {
        setStatus(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // WebSocket updates
  const handleUpdate = useCallback((data: unknown) => {
    setStatus(data as StatusResponse);
  }, []);

  useEffect(() => {
    return subscribe("status", handleUpdate);
  }, [subscribe, handleUpdate]);

  return { status, loading };
}
