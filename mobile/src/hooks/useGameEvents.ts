import { useEffect, useRef, useState } from "react";
import { API_URL } from "../api/client";
import { listEvents } from "../api/games";
import { createWebSocketTicket } from "../api/websocketTickets";
import type { GameEvent } from "../types/game";
import { captureError, captureMessage } from "../utils/errorReporter";

const MAX_RECONNECT_DELAY_MS = 10_000;
const POLL_DELAY_MS = 2_500;
const FALLBACK_AFTER_FAILURES = 2;
const CONNECT_TIMEOUT_MS = 8_000;

function wsUrl(gameId: string, ticket: string, afterId: number) {
  const base = API_URL.replace(/^http/, "ws");
  return `${base}/ws/games/${encodeURIComponent(gameId)}?ticket=${encodeURIComponent(ticket)}&after_id=${afterId}`;
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
  const onEventsRef = useRef(onEvents);
  const seenIds = useRef(new Set<number>());
  const lastId = useRef(0);
  const connectionGeneration = useRef(0);

  useEffect(() => {
    onEventsRef.current = onEvents;
  }, [onEvents]);

  useEffect(() => {
    const generation = ++connectionGeneration.current;
    seenIds.current = new Set<number>();
    lastId.current = 0;
    setLastEventId(0);
    setLastEventType(null);
    setConnected(false);
    setFallbackPolling(false);

    if (!enabled || !gameId || !userId) return;
    const activeGameId = gameId;
    let closed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let socketDeadlineTimer: ReturnType<typeof setTimeout> | null = null;
    let failures = 0;
    let pollInFlight = false;
    let pollingEnabled = false;
    const ticketControllers = new Set<AbortController>();
    const pollControllers = new Set<AbortController>();
    const isCurrent = () => !closed && generation === connectionGeneration.current;

    function emitDedup(events: GameEvent[]) {
      if (!isCurrent()) return;
      const fresh = events.filter((event) => {
        if (event.game_id !== activeGameId || seenIds.current.has(event.id)) return false;
        seenIds.current.add(event.id);
        lastId.current = Math.max(lastId.current, event.id);
        setLastEventId(lastId.current);
        setLastEventType(event.event_type);
        return true;
      });
      if (fresh.length && isCurrent()) onEventsRef.current(fresh);
    }

    function schedulePoll() {
      if (!isCurrent() || !pollingEnabled || pollTimer) return;
      pollTimer = setTimeout(async () => {
        pollTimer = null;
        if (!isCurrent() || !pollingEnabled || pollInFlight) return schedulePoll();
        pollInFlight = true;
        const controller = new AbortController();
        pollControllers.add(controller);
        try {
          const events = await listEvents(activeGameId, lastId.current, controller.signal);
          emitDedup(events);
        } catch (error) {
          if (isCurrent() && !controller.signal.aborted) {
            captureError(error, { area: "event_polling", gameId: activeGameId });
          }
        } finally {
          pollControllers.delete(controller);
          pollInFlight = false;
          schedulePoll();
        }
      }, POLL_DELAY_MS);
    }

    function enterFallback() {
      if (!isCurrent()) return;
      pollingEnabled = true;
      setFallbackPolling(true);
      schedulePoll();
    }

    function scheduleReconnect() {
      if (!isCurrent() || reconnectTimer) return;
      const delay = Math.min(1_000 * 2 ** Math.min(failures, 4), MAX_RECONNECT_DELAY_MS);
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, delay);
    }

    async function connect() {
      if (!isCurrent()) return;
      const ticketController = new AbortController();
      ticketControllers.add(ticketController);
      const ticketDeadline = setTimeout(() => ticketController.abort(), CONNECT_TIMEOUT_MS);
      try {
        const issued = await createWebSocketTicket(activeGameId, ticketController.signal);
        if (!isCurrent()) return;
        const candidate = new WebSocket(wsUrl(activeGameId, issued.ticket, lastId.current));
        socket = candidate;
        socketDeadlineTimer = setTimeout(() => {
          if (!isCurrent() || socket !== candidate || candidate.readyState === WebSocket.OPEN) return;
          socket = null;
          failures += 1;
          candidate.close();
          setConnected(false);
          if (failures >= FALLBACK_AFTER_FAILURES) enterFallback();
          scheduleReconnect();
        }, CONNECT_TIMEOUT_MS);
        candidate.onopen = () => {
          if (!isCurrent() || socket !== candidate) return candidate.close();
          if (socketDeadlineTimer) clearTimeout(socketDeadlineTimer);
          socketDeadlineTimer = null;
          failures = 0;
          setConnected(true);
          setFallbackPolling(false);
          pollingEnabled = false;
          if (pollTimer) clearTimeout(pollTimer);
          pollTimer = null;
          for (const controller of pollControllers) controller.abort();
          pollControllers.clear();
        };
        candidate.onmessage = (message) => {
          if (!isCurrent() || socket !== candidate) return;
          try {
            const parsed = JSON.parse(message.data);
            if (parsed.type === "event") emitDedup([parsed.event]);
          } catch (error) {
            captureError(error, { area: "websocket_parse", gameId: activeGameId });
          }
        };
        candidate.onerror = () => {
          if (!isCurrent() || socket !== candidate) return;
          captureMessage("WebSocket error", { area: "websocket", gameId: activeGameId });
        };
        candidate.onclose = () => {
          if (!isCurrent() || socket !== candidate) return;
          if (socketDeadlineTimer) clearTimeout(socketDeadlineTimer);
          socketDeadlineTimer = null;
          socket = null;
          failures += 1;
          setConnected(false);
          if (failures >= FALLBACK_AFTER_FAILURES) enterFallback();
          scheduleReconnect();
        };
      } catch (error) {
        if (!isCurrent()) return;
        failures += 1;
        setConnected(false);
        if (failures >= FALLBACK_AFTER_FAILURES) enterFallback();
        captureError(error, { area: "websocket_ticket", gameId: activeGameId, failures });
        scheduleReconnect();
      } finally {
        clearTimeout(ticketDeadline);
        ticketControllers.delete(ticketController);
      }
    }

    void connect();
    return () => {
      if (closed) return;
      closed = true;
      pollingEnabled = false;
      for (const controller of ticketControllers) controller.abort();
      ticketControllers.clear();
      for (const controller of pollControllers) controller.abort();
      pollControllers.clear();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (pollTimer) clearTimeout(pollTimer);
      if (socketDeadlineTimer) clearTimeout(socketDeadlineTimer);
      socket?.close();
    };
  }, [enabled, gameId, userId]);

  return { connected, fallbackPolling, lastEventId, lastEventType };
}
