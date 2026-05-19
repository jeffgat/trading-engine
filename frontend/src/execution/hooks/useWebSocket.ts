import { useCallback, useEffect, useRef, useState } from "react";
import type { WsMessage } from "@/execution/lib/types";

type MessageHandler = (data: unknown) => void;

function resolveWebSocketUrl() {
  const configuredUrl = import.meta.env.VITE_EXEC_WS_URL?.trim();
  if (configuredUrl) return configuredUrl;

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/exec-api/ws`;
}

export function useWebSocket() {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const listenersRef = useRef(new Map<string, Set<MessageHandler>>());
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let delay = 1000;
    let disposed = false;

    function connect() {
      if (disposed) return;

      const ws = new WebSocket(resolveWebSocketUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        delay = 1000;
      };

      ws.onclose = () => {
        setConnected(false);
        if (!disposed) {
          reconnectRef.current = setTimeout(connect, delay);
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

    connect();

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

  return { connected, subscribe };
}
