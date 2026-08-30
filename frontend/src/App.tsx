import { useEffect, useMemo, useState } from "react";

import { fetchIncidents } from "./api/incidents";
import { IncidentCard } from "./components/IncidentCard";
import { IncidentDetails } from "./components/IncidentDetails";
import {
  IncidentFilters,
  type SeverityFilter,
  type StatusFilter,
} from "./components/IncidentFilters";
import type { Incident } from "./types/incident";

type RequestStatus = "loading" | "success" | "error";

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [requestStatus, setRequestStatus] = useState<RequestStatus>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(
    null,
  );

  useEffect(() => {
    const controller = new AbortController();

    async function loadIncidents() {
      try {
        setRequestStatus("loading");
        setErrorMessage("");

        const receivedIncidents = await fetchIncidents(controller.signal);
        setIncidents(receivedIncidents);
        setRequestStatus("success");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setErrorMessage(
          error instanceof Error ? error.message : "Unable to load incidents",
        );
        setRequestStatus("error");
      }
    }

    void loadIncidents();

    return () => controller.abort();
  }, []);

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

  const selectedIncident = useMemo(
    () =>
      filteredIncidents.find(
        (incident) => incident.id === selectedIncidentId,
      ) ?? null,
    [filteredIncidents, selectedIncidentId],
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
        <div className="live-indicator" aria-label="Network feed online">
          <span /> Network feed online
        </div>
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
