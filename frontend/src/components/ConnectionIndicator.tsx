import type { ConnectionState } from "../hooks/useIncidentBoard";

type ConnectionIndicatorProps = {
  connection: ConnectionState;
};

const LABELS: Record<ConnectionState, string> = {
  connecting: "Connecting to network feed",
  live: "Network feed live",
  offline: "Network feed offline — retrying",
};

export function ConnectionIndicator({ connection }: ConnectionIndicatorProps) {
  return (
    <div
      className={`live-indicator live-indicator--${connection}`}
      // Announced to screen readers when it changes, because an operator needs
      // to know the board has stopped updating regardless of how they read it.
      role="status"
      aria-live="polite"
    >
      <span aria-hidden="true" />
      {LABELS[connection]}
    </div>
  );
}
