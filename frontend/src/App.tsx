import { useMemo, useState } from "react";

import { ConnectionIndicator } from "./components/ConnectionIndicator";
import { IncidentCard } from "./components/IncidentCard";
import { IncidentDetails } from "./components/IncidentDetails";
import {
  IncidentFilters,
  type SeverityFilter,
  type StatusFilter,
} from "./components/IncidentFilters";
import { LiveEventFeed } from "./components/LiveEventFeed";
import { useIncidentBoard } from "./hooks/useIncidentBoard";

export default function App() {
  const { incidents, requestStatus, errorMessage, connection, feed } =
    useIncidentBoard();
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(
    null,
  );

  const openIncidents = useMemo(
    () => incidents.filter((incident) => incident.status !== "resolved"),
    [incidents],
  );

  const filteredIncidents = useMemo(
    () =>
      incidents.filter((incident) => {
        const matchesSeverity =
          severityFilter === "all" || incident.severity === severityFilter;
        const matchesStatus =
          statusFilter === "all" || incident.status === statusFilter;

        return matchesSeverity && matchesStatus;
      }),
    [incidents, severityFilter, statusFilter],
  );

  // Derived from every incident, not the filtered subset: changing a filter
  // should not silently close the detail pane the engineer is reading. This
  // also keeps the pane showing live updates for an incident that a filter
  // would currently exclude.
  const selectedIncident = useMemo(
    () => incidents.find((incident) => incident.id === selectedIncidentId) ?? null,
    [incidents, selectedIncidentId],
  );

  const criticalIncidents = openIncidents.filter(
    (incident) => incident.severity === "critical",
  ).length;

  const affectedSubscribers = openIncidents.reduce(
    (total, incident) => total + incident.affected_subscribers,
    0,
  );

  function clearFilters() {
    setSeverityFilter("all");
    setStatusFilter("all");
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Telecom network operations</p>
          <h1>SignalOps AI</h1>
          <p className="hero__summary">
            Correlate network alarms, understand customer impact, and guide
            engineers toward faster incident resolution.
          </p>
        </div>
        <ConnectionIndicator connection={connection} />
      </header>

      <main>
        <section className="metrics" aria-label="Incident summary">
          <article className="metric-card">
            <span>Open incidents</span>
            <strong>{openIncidents.length}</strong>
          </article>
          <article className="metric-card">
            <span>Critical incidents</span>
            <strong>{criticalIncidents}</strong>
          </article>
          <article className="metric-card">
            <span>Affected subscribers</span>
            <strong>{affectedSubscribers.toLocaleString()}</strong>
          </article>
        </section>

        <LiveEventFeed entries={feed} />

        <section className="incidents-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current operations</p>
              <h2>Network incidents</h2>
            </div>
            {requestStatus === "success" && (
              <span>
                {filteredIncidents.length} of {incidents.length} shown
              </span>
            )}
          </div>

          {requestStatus === "success" && incidents.length > 0 && (
            <IncidentFilters
              severity={severityFilter}
              status={statusFilter}
              onSeverityChange={setSeverityFilter}
              onStatusChange={setStatusFilter}
              onClear={clearFilters}
            />
          )}

          {requestStatus === "loading" && (
            <div className="state-panel" role="status">
              Loading incidents from the network operations API…
            </div>
          )}

          {requestStatus === "error" && (
            <div className="state-panel state-panel--error" role="alert">
              <strong>Could not load incidents.</strong>
              <span>{errorMessage}</span>
            </div>
          )}

          {requestStatus === "success" && incidents.length === 0 && (
            <div className="state-panel">
              No incidents are currently reported.
            </div>
          )}

          {requestStatus === "success" &&
            incidents.length > 0 &&
            filteredIncidents.length === 0 && (
              <div className="state-panel">
                <strong>No incidents match these filters.</strong>
                <span>Clear or change a filter to restore the list.</span>
              </div>
            )}

          {requestStatus === "success" && filteredIncidents.length > 0 && (
            <div
              className={`operations-layout${
                selectedIncident ? " operations-layout--with-details" : ""
              }`}
            >
              <div className="incident-grid">
                {filteredIncidents.map((incident) => (
                  <IncidentCard
                    key={incident.id}
                    incident={incident}
                    isSelected={incident.id === selectedIncidentId}
                    onSelect={setSelectedIncidentId}
                  />
                ))}
              </div>

              {selectedIncident && (
                <IncidentDetails
                  incident={selectedIncident}
                  onClose={() => setSelectedIncidentId(null)}
                />
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
