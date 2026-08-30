import type { Incident } from "../types/incident";

type IncidentCardProps = {
  incident: Incident;
  isSelected: boolean;
  onSelect: (incidentId: string) => void;
};

const dateFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function IncidentCard({
  incident,
  isSelected,
  onSelect,
}: IncidentCardProps) {
  return (
    <article
      className={`incident-card${isSelected ? " incident-card--selected" : ""}`}
    >
      <div className="incident-card__topline">
        <div>
          <p className="incident-card__id">{incident.id}</p>
          <h3>{incident.title}</h3>
        </div>
        <span className={`severity severity--${incident.severity}`}>
          {incident.severity}
        </span>
      </div>

      <dl className="incident-card__details">
        <div>
          <dt>Site</dt>
          <dd>{incident.site_id}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{incident.status}</dd>
        </div>
        <div>
          <dt>Affected subscribers</dt>
          <dd>{incident.affected_subscribers.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Opened</dt>
          <dd>{dateFormatter.format(new Date(incident.opened_at))}</dd>
        </div>
      </dl>

      <div className="incident-card__cause">
        <span>Probable cause</span>
        <strong>{incident.probable_cause}</strong>
      </div>

      <button
        className="incident-card__action"
        type="button"
        onClick={() => onSelect(incident.id)}
        aria-pressed={isSelected}
      >
        {isSelected ? "Details selected" : "View incident details"}
      </button>
    </article>
  );
}
