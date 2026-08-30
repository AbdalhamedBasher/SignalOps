import {
  incidentSeverities,
  incidentStatuses,
  type IncidentSeverity,
  type IncidentStatus,
} from "../types/incident";

export type SeverityFilter = "all" | IncidentSeverity;
export type StatusFilter = "all" | IncidentStatus;

type IncidentFiltersProps = {
  severity: SeverityFilter;
  status: StatusFilter;
  onSeverityChange: (severity: SeverityFilter) => void;
  onStatusChange: (status: StatusFilter) => void;
  onClear: () => void;
};

export function IncidentFilters({
  severity,
  status,
  onSeverityChange,
  onStatusChange,
  onClear,
}: IncidentFiltersProps) {
  const hasActiveFilters = severity !== "all" || status !== "all";

  return (
    <div className="incident-filters" aria-label="Incident filters">
      <label>
        <span>Severity</span>
        <select
          value={severity}
          onChange={(event) =>
            onSeverityChange(event.target.value as SeverityFilter)
          }
        >
          <option value="all">All severities</option>
          {incidentSeverities.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>Status</span>
        <select
          value={status}
          onChange={(event) =>
            onStatusChange(event.target.value as StatusFilter)
          }
        >
          <option value="all">All statuses</option>
          {incidentStatuses.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <button
        className="filter-clear"
        type="button"
        onClick={onClear}
        disabled={!hasActiveFilters}
      >
        Clear filters
      </button>
    </div>
  );
}
