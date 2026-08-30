import { useEffect, useState } from "react";

import { INCIDENT_FEED_URL, fetchIncidents } from "../api/incidents";
import {
  isIncidentEvent,
  type Incident,
  type IncidentEventType,
} from "../types/incident";

export type RequestStatus = "loading" | "success" | "error";
export type ConnectionState = "connecting" | "live" | "offline";

export type FeedEntry = {
  key: string;
  type: IncidentEventType;
  incidentId: string;
  title: string;
  siteId: string;
  receivedAt: Date;
};

const MAX_FEED_ENTRIES = 8;
const FIRST_RETRY_DELAY_MS = 1_000;
const MAX_RETRY_DELAY_MS = 30_000;

/**
 * Back off further after each failure, but never past half a minute, and add
 * jitter. Without the jitter, every dashboard knocked offline by one restart
 * would reconnect on exactly the same schedule and hit the server together.
 */
function retryDelay(attempt: number): number {
  const growth = Math.min(
    MAX_RETRY_DELAY_MS,
    FIRST_RETRY_DELAY_MS * 2 ** attempt,
  );

  return growth / 2 + Math.random() * (growth / 2);
}

function upsert(incidents: Incident[], incoming: Incident): Incident[] {
  const withoutIncoming = incidents.filter(
    (incident) => incident.id !== incoming.id,
  );

  // Re-sorted rather than inserted in place, because an incident's opened_at
  // can move earlier when a late alarm turns out to predate it. This keeps the
  // board in the same order the API would return.
  return [...withoutIncoming, incoming].sort((first, second) =>
    second.opened_at.localeCompare(first.opened_at),
  );
}

export function useIncidentBoard() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [requestStatus, setRequestStatus] = useState<RequestStatus>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [feed, setFeed] = useState<FeedEntry[]>([]);

  useEffect(() => {
    // React runs effects twice in development StrictMode. Without this flag the
    // torn-down first run would keep reconnecting in the background forever.
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let failedAttempts = 0;

    const controller = new AbortController();

    async function loadSnapshot() {
      try {
        const received = await fetchIncidents(controller.signal);

        if (disposed) {
          return;
        }

        setIncidents(received);
        setErrorMessage("");
        setRequestStatus("success");
      } catch (error) {
        if (disposed || (error instanceof DOMException && error.name === "AbortError")) {
          return;
        }

        setErrorMessage(
          error instanceof Error ? error.message : "Unable to load incidents",
        );
        setRequestStatus("error");
      }
    }

    function scheduleReconnect() {
      retryTimer = setTimeout(connect, retryDelay(failedAttempts));
      failedAttempts += 1;
    }

    function connect() {
      if (disposed) {
        return;
      }

      setConnection("connecting");
      socket = new WebSocket(INCIDENT_FEED_URL);

      socket.onopen = () => {
        if (disposed) {
          return;
        }

        failedAttempts = 0;
        setConnection("live");

        // A socket only carries what happens while it is open, so whatever was
        // missed while disconnected is recovered by re-reading the board.
        void loadSnapshot();
      };

      socket.onmessage = (message) => {
        if (disposed) {
          return;
        }

        let payload: unknown;

        try {
          payload = JSON.parse(message.data as string);
        } catch {
          return;
        }

        // The socket is exactly as untrusted as the HTTP response.
        if (!isIncidentEvent(payload)) {
          return;
        }

        setIncidents((current) => upsert(current, payload.incident));
        setFeed((current) =>
          [
            {
              key: `${payload.incident.id}-${Date.now()}-${Math.random()}`,
              type: payload.type,
              incidentId: payload.incident.id,
              title: payload.incident.title,
              siteId: payload.incident.site_id,
              receivedAt: new Date(),
            },
            ...current,
          ].slice(0, MAX_FEED_ENTRIES),
        );
      };

      socket.onclose = () => {
        if (disposed) {
          return;
        }

        setConnection("offline");
        scheduleReconnect();
      };

      socket.onerror = () => {
        // An error is always followed by a close event, which is where the
        // reconnect is scheduled. Handling it here too would double-book it.
        socket?.close();
      };
    }

    // Load once immediately so the board is usable even if the socket never
    // opens; the connection indicator is what tells the operator it is stale.
    void loadSnapshot();
    connect();

    return () => {
      disposed = true;
      controller.abort();
      clearTimeout(retryTimer);

      if (socket) {
        // Detach first: closing otherwise fires onclose and books a reconnect
        // for a component that is going away.
        socket.onopen = null;
        socket.onmessage = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.close();
      }
    };
  }, []);

  return { incidents, requestStatus, errorMessage, connection, feed };
}
