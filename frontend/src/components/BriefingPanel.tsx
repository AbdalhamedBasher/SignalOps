import { useEffect, useState } from "react";

import { fetchBriefing, requestBriefing } from "../api/recommendations";
import type { Briefing } from "../types/recommendation";

type BriefingPanelProps = {
  incidentId: string;
  hasRecommendations: boolean;
};

const timeFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function BriefingPanel({
  incidentId,
  hasRecommendations,
}: BriefingPanelProps) {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        setErrorMessage("");
        setBriefing(await fetchBriefing(incidentId, controller.signal));
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setErrorMessage(
          error instanceof Error ? error.message : "Unable to load the briefing",
        );
      }
    }

    void load();

    return () => controller.abort();
  }, [incidentId]);

  async function generate() {
    try {
      setIsGenerating(true);
      setErrorMessage("");
      setBriefing(await requestBriefing(incidentId));
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Could not generate a briefing",
      );
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <section className="briefing" aria-labelledby="briefing-title">
      <div className="briefing__heading">
        <span id="briefing-title">Incident briefing</span>
        <button
          className="briefing__generate"
          type="button"
          onClick={() => void generate()}
          disabled={isGenerating || !hasRecommendations}
        >
          {isGenerating ? "Writing…" : briefing ? "Regenerate" : "Generate"}
        </button>
      </div>

      {errorMessage && (
        <p className="briefing__error" role="alert">
          {errorMessage}
        </p>
      )}

      {!briefing && !errorMessage && (
        <p className="briefing__idle">
          {hasRecommendations
            ? "Generate a short orientation over the runbook sections matched above."
            : "Retrieve runbook guidance first — a briefing only summarises procedures that have already been matched."}
        </p>
      )}

      {briefing && (
        <>
          {/* Stated plainly and always. An engineer must never have to guess
              whether they are reading an approved procedure or a summary of
              one. */}
          <p className="briefing__provenance">
            Written by {briefing.model} from the sections cited below · never a
            substitute for reading them
          </p>

          <p className="briefing__summary">{briefing.summary}</p>

          {briefing.first_actions.length > 0 && (
            <ol className="briefing__actions">
              {briefing.first_actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ol>
          )}

          {briefing.gaps && (
            <p className="briefing__gaps">
              <strong>Not covered by the runbooks:</strong> {briefing.gaps}
            </p>
          )}

          <p className="briefing__citations">
            Drawn from{" "}
            {briefing.cited_section_ids.length > 0
              ? briefing.cited_section_ids.join(", ")
              : "no sections"}
            <span aria-hidden="true"> · </span>
            <time dateTime={briefing.generated_at}>
              {timeFormatter.format(new Date(briefing.generated_at))}
            </time>
          </p>
        </>
      )}
    </section>
  );
}
