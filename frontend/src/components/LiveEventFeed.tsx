import type { FeedEntry } from "../hooks/useIncidentBoard";

type LiveEventFeedProps = {
  entries: FeedEntry[];
};

const timeFormatter = new Intl.DateTimeFormat("en", {
  timeStyle: "medium",
});

const EVENT_LABELS: Record<FeedEntry["type"], string> = {
  "incident.opened": "opened",
  "incident.updated": "updated",
};

export function LiveEventFeed({ entries }: LiveEventFeedProps) {
  return (
    <section
      className={`event-feed${entries.length === 0 ? " event-feed--idle" : ""}`}
      aria-labelledby="event-feed-title"
    >
      <div className="event-feed__heading">
        <span id="event-feed-title">Live activity</span>
        {entries.length > 0 && (
          <span className="event-feed__count">{entries.length}</span>
        )}
      </div>

      {entries.length === 0 ? (
        <p className="event-feed__idle">Waiting for network events</p>
      ) : (
        <ol className="event-feed__list">
          {entries.map((entry) => (
            <li className="event-feed__item" key={entry.key}>
              <span
                className={`event-feed__tag event-feed__tag--${
                  entry.type === "incident.opened" ? "opened" : "updated"
                }`}
              >
                {EVENT_LABELS[entry.type]}
              </span>
              <span className="event-feed__detail">
                <strong>{entry.incidentId}</strong> {entry.title} at{" "}
                {entry.siteId}
              </span>
              <time
                className="event-feed__time"
                dateTime={entry.receivedAt.toISOString()}
              >
                {timeFormatter.format(entry.receivedAt)}
              </time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
