import { useCallback, useEffect, useRef, useState } from "react";
import { getApiAuthToken } from "@/auth/apiAuth";
import type { WsMessage } from "@/execution/lib/types";

type MessageHandler = (data: unknown) => void;
export type WebSocketStatus = "connecting" | "connected" | "reconnecting";

async function resolveWebSocketUrl() {
  const configuredUrl = import.meta.env.VITE_EXEC_WS_URL?.trim();
  const token = await getApiAuthToken();
  if (configuredUrl) {
    const url = new URL(configuredUrl);
    if (token) url.searchParams.set("token", token);
    return url.toString();
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${protocol}//${window.location.host}/exec-api/ws`);
  if (token) url.searchParams.set("token", token);
  return url.toString();
}

export function useWebSocket() {
  const [status, setStatus] = useState<WebSocketStatus>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const listenersRef = useRef(new Map<string, Set<MessageHandler>>());
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let delay = 1000;
    let disposed = false;

    async function connect() {
      if (disposed) return;

      const ws = new WebSocket(await resolveWebSocketUrl());
      if (disposed) {
        ws.close();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        delay = 1000;
      };

      ws.onclose = () => {
        if (!disposed) {
          setStatus("reconnecting");
          reconnectRef.current = setTimeout(() => void connect(), delay);
          delay = Math.min(delay * 2, 10000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WsMessage;
          const handlers = listenersRef.current.get(msg.type);
          if (handlers) {
            handlers.forEach((cb) => cb(msg.data));
          }
        } catch {
          // ignore malformed messages
        }
      };
    }

    void connect();

    return () => {
      disposed = true;
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, []);

  const subscribe = useCallback(
    (type: string, callback: MessageHandler) => {
      if (!listenersRef.current.has(type)) {
        listenersRef.current.set(type, new Set());
      }
      listenersRef.current.get(type)!.add(callback);

      return () => {
        listenersRef.current.get(type)?.delete(callback);
      };
    },
    [],
  );

  return { connected: status === "connected", status, subscribe };
}
