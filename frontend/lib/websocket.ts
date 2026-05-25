"use client";
/**
 * useRunStream — React hook that connects to the backend WebSocket for a run
 * and streams events in real time.
 *
 * ws://localhost:8000/ws/runs/{runId}
 *
 * Returns { events, status, cost, isConnected }
 *  - events: ordered list of raw event objects received from the server
 *  - status: last run status seen in any event ("pending"|"running"|"completed"|"failed")
 *  - cost: latest total_cost_usd seen in any run_completed event
 *  - isConnected: whether the socket is currently open
 */

import { useEffect, useRef, useState, useCallback } from "react";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

export interface StreamEvent {
  event_type: string;
  run_id: string;
  timestamp: string;
  data: Record<string, unknown>;
}

export type RunStreamStatus = "pending" | "running" | "completed" | "failed" | "idle";

export interface UseRunStreamResult {
  events: StreamEvent[];
  status: RunStreamStatus;
  cost: number;
  isConnected: boolean;
  clearEvents: () => void;
}

export function useRunStream(runId: string | null): UseRunStreamResult {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [status, setStatus] = useState<RunStreamStatus>("idle");
  const [cost, setCost] = useState<number>(0);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setStatus("idle");
    setCost(0);
  }, []);

  useEffect(() => {
    if (!runId) return;

    const url = `${WS_BASE}/ws/runs/${runId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setStatus("running");
    };

    ws.onmessage = (raw) => {
      try {
        const evt: StreamEvent = JSON.parse(raw.data as string);
        setEvents((prev) => [...prev, evt]);

        // Update status from event type
        switch (evt.event_type) {
          case "run_started":
            setStatus("running");
            break;
          case "run_completed":
            setStatus("completed");
            // Backend broadcasts total_tokens and optionally final_response
            if (typeof evt.data.total_cost_usd === "number") {
              setCost(evt.data.total_cost_usd as number);
            }
            break;
          case "run_failed":
            setStatus("failed");
            break;
        }
      } catch {
        // Ignore malformed frames
      }
    };

    ws.onerror = () => {
      setIsConnected(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId]);

  return { events, status, cost, isConnected, clearEvents };
}
