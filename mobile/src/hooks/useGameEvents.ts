import { useEffect, useRef, useState } from "react";
import { API_URL } from "../api/client";
import { listEvents } from "../api/games";
import type { GameEvent } from "../types/game";
import { captureError, captureMessage } from "../utils/errorReporter";

function wsUrl(gameId: string, userId: string, afterId: number) {
  const base = API_URL.replace(/^http/, "ws");
  return `${base}/ws/games/${gameId}?user_id=${encodeURIComponent(userId)}&after_id=${afterId}`;
}

export function useGameEvents({
  gameId,
  userId,
  enabled,
  onEvents,
}: {
  gameId: string | null;
  userId: string | null;
  enabled: boolean;
  onEvents: (events: GameEvent[]) => void;
}) {
  const [connected, setConnected] = useState(false);
  const [fallbackPolling, setFallbackPolling] = useState(false);
  const [lastEventId, setLastEventId] = useState(0);
  const [lastEventType, setLastEventType] = useState<string | null>(null);
  const seenIds = useRef(new Set<number>());
  const lastId = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled || !gameId || !userId) return;
    const activeGameId = gameId;
    const activeUserId = userId;
    let socket: WebSocket | null = null;
    let closed = false;
    let failures = 0;

    function emitDedup(events: GameEvent[]) {
      const fresh = events.filter((event) => {
        if (seenIds.current.has(event.id)) return false;
        seenIds.current.add(event.id);
        lastId.current = Math.max(lastId.current, event.id);
        setLastEventId(lastId.current);
        setLastEventType(event.event_type);
        return true;
      });
      if (fresh.length) onEvents(fresh);
    }

    function connect() {
      socket = new WebSocket(wsUrl(activeGameId, activeUserId, lastId.current));
      socket.onopen = () => {
        failures = 0;
        setConnected(true);
        setFallbackPolling(false);
      };
      socket.onmessage = (message) => {
        try {
          const parsed = JSON.parse(message.data);
          if (parsed.type === "event") emitDedup([parsed.event]);
        } catch (error) {
          captureError(error, { area: "websocket_parse", gameId: activeGameId });
        }
      };
      socket.onerror = () => {
        failures += 1;
        captureMessage("WebSocket error", { area: "websocket", gameId: activeGameId, failures });
      };
      socket.onclose = () => {
        setConnected(false);
        if (closed) return;
        if (failures >= 2) setFallbackPolling(true);
        reconnectTimer.current = setTimeout(connect, Math.min(1000 * (failures + 1), 5000));
      };
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      socket?.close();
    };
  }, [enabled, gameId, userId, onEvents]);

  useEffect(() => {
    if (!fallbackPolling || !enabled || !gameId) return;
    const activeGameId = gameId;
    const interval = setInterval(async () => {
      try {
        const events = await listEvents(activeGameId, lastId.current);
        const fresh = events.filter((event) => {
          if (seenIds.current.has(event.id)) return false;
          seenIds.current.add(event.id);
          lastId.current = Math.max(lastId.current, event.id);
          setLastEventId(lastId.current);
          setLastEventType(event.event_type);
          return true;
        });
        if (fresh.length) onEvents(fresh);
      } catch (error) {
        captureError(error, { area: "event_polling", gameId: activeGameId });
      }
    }, 2500);
    return () => clearInterval(interval);
  }, [fallbackPolling, enabled, gameId, onEvents]);

  return { connected, fallbackPolling, lastEventId, lastEventType };
}
