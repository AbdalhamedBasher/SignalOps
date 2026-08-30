import type { Incident } from "../types/incident";

type IncidentDetailsProps = {
  incident: Incident;
  onClose: () => void;
};

const dateFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
});

// Seconds matter here: alarms in one incident often land inside the same
// minute, and their order is the evidence for what caused what.
const timeFormatter = new Intl.DateTimeFormat("en", {
  timeStyle: "medium",
});

export function IncidentDetails({ incident, onClose }: IncidentDetailsProps) {
  // Copy before sorting: `sort` mutates in place, and `incident.alarms` is
  // owned by App's state. Sorting it directly would mutate state behind React's
  // back. Not memoized on purpose — this list is small and only re-renders when
  // the engineer picks a different incident.
  const alarmsOldestFirst = [...incident.alarms].sort(
    (first, second) =>
      Date.parse(first.occurred_at) - Date.parse(second.occurred_at),
  );

  return (
    <aside
      className="incident-details"
      aria-labelledby="selected-incident-title"
    >
      <div className="incident-details__header">
        <div>
          <p className="eyebrow">Selected incident</p>
          <h2 id="selected-incident-title">{incident.title}</h2>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={onClose}
          aria-label="Close incident details"
        >
          ×
        </button>
      </div>

      <p className="incident-details__id">{incident.id}</p>

      <dl className="incident-details__facts">
        <div>
          <dt>Site</dt>
          <dd>{incident.site_id}</dd>
        </div>
        <div>
          <dt>Severity</dt>
          <dd>
            <span className={`severity severity--${incident.severity}`}>
              {incident.severity}
            </span>
          </dd>
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

      <div className="incident-details__cause">
        <span>Probable cause</span>
        <strong>{incident.probable_cause}</strong>
      </div>

      <section className="alarm-timeline" aria-labelledby="alarm-timeline-title">
        <div className="alarm-timeline__heading">
          <span id="alarm-timeline-title">Correlated alarms</span>
          <span className="alarm-timeline__count">
            {incident.alarms.length}
          </span>
        </div>

        {/*
          TODO(you): render an empty state when `incident.alarms.length === 0`.
          Show something like "No alarms were correlated to this incident yet."
          using the existing `.state-panel` class, and make sure the <ol> below
          does not render in that case.
          Hint: the four states this project cares about are loading, error,
          empty, success — see rule 5 in the README. This is the empty one.
        */}

        <ol className="alarm-timeline__list">
          {alarmsOldestFirst.map((alarm, index) => (
            <li className="alarm-timeline__item" key={alarm.id}>
              <span className="alarm-timeline__marker" aria-hidden="true" />
              <div className="alarm-timeline__body">
                <div className="alarm-timeline__topline">
                  <code className="alarm-timeline__code">{alarm.code}</code>
                  {index === 0 && (
                    <span className="alarm-timeline__badge">first signal</span>
                  )}
                </div>
                <p className="alarm-timeline__message">{alarm.message}</p>
                <time
                  className="alarm-timeline__time"
                  dateTime={alarm.occurred_at}
                  title={dateFormatter.format(new Date(alarm.occurred_at))}
                >
                  {timeFormatter.format(new Date(alarm.occurred_at))}
                </time>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}
