import { useEffect, useState } from "react";

import {
  decideRecommendation,
  fetchRecommendations,
  requestRecommendations,
} from "../api/recommendations";
import type { Recommendation } from "../types/recommendation";
import { BriefingPanel } from "./BriefingPanel";

type RecommendationPanelProps = {
  incidentId: string;
};

const STATUS_LABELS: Record<Recommendation["status"], string> = {
  proposed: "awaiting review",
  approved: "approved",
  rejected: "rejected",
};

export function RecommendationPanel({ incidentId }: RecommendationPanelProps) {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRetrieving, setIsRetrieving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [engineer, setEngineer] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        setIsLoading(true);
        setErrorMessage("");
        setRecommendations(
          await fetchRecommendations(incidentId, controller.signal),
        );
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setErrorMessage(
          error instanceof Error ? error.message : "Unable to load guidance",
        );
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    }

    void load();

    return () => controller.abort();
  }, [incidentId]);

  async function retrieve() {
    try {
      setIsRetrieving(true);
      setErrorMessage("");
      setRecommendations(await requestRecommendations(incidentId));
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Unable to retrieve guidance",
      );
    } finally {
      setIsRetrieving(false);
    }
  }

  async function decide(recommendation: Recommendation, approved: boolean) {
    try {
      setPendingId(recommendation.id);
      setErrorMessage("");

      const decided = await decideRecommendation(recommendation.id, {
        approved,
        decidedBy: engineer.trim(),
      });

      setRecommendations((current) =>
        current.map((item) => (item.id === decided.id ? decided : item)),
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Unable to record the decision",
      );
    } finally {
      setPendingId(null);
    }
  }

  // The backend rejects an unattributed decision, so the buttons stay disabled
  // until there is a name to record. An audit trail of "someone" is worthless.
  const canDecide = engineer.trim().length > 0;

  return (
    <>
    <section className="runbook" aria-labelledby="runbook-title">
      <div className="runbook__heading">
        <span id="runbook-title">Runbook guidance</span>
        <button
          className="runbook__retrieve"
          type="button"
          onClick={() => void retrieve()}
          disabled={isRetrieving}
        >
          {isRetrieving ? "Retrieving…" : "Retrieve guidance"}
        </button>
      </div>

      {errorMessage && (
        <p className="runbook__error" role="alert">
          {errorMessage}
        </p>
      )}

      {isLoading && <p className="runbook__idle">Loading guidance…</p>}

      {!isLoading && recommendations.length === 0 && (
        <p className="runbook__idle">
          No approved procedure has been matched to this incident yet. Use
          “Retrieve guidance” to search the runbooks for its alarm codes.
        </p>
      )}

      {recommendations.length > 0 && (
        <>
          <label className="runbook__engineer">
            <span>Deciding as</span>
            <input
              type="text"
              value={engineer}
              placeholder="your name"
              onChange={(event) => setEngineer(event.target.value)}
            />
          </label>

          <ol className="runbook__list">
            {recommendations.map((recommendation) => (
              <li className="runbook__item" key={recommendation.id}>
                <div className="runbook__topline">
                  <span
                    className={`runbook__status runbook__status--${recommendation.status}`}
                  >
                    {STATUS_LABELS[recommendation.status]}
                  </span>
                  <span className="runbook__id">{recommendation.id}</span>
                </div>

                <h4 className="runbook__section-heading">
                  {recommendation.section.heading}
                </h4>

                <p className="runbook__citation">
                  {recommendation.section.runbook_title}
                  <span aria-hidden="true"> · </span>
                  <code>{recommendation.section.source_name}</code>
                </p>

                <p className="runbook__rationale">{recommendation.rationale}</p>

                <pre className="runbook__body">{recommendation.section.body}</pre>

                {recommendation.status === "proposed" ? (
                  <div className="runbook__actions">
                    <button
                      className="runbook__approve"
                      type="button"
                      disabled={!canDecide || pendingId === recommendation.id}
                      onClick={() => void decide(recommendation, true)}
                    >
                      Approve
                    </button>
                    <button
                      className="runbook__reject"
                      type="button"
                      disabled={!canDecide || pendingId === recommendation.id}
                      onClick={() => void decide(recommendation, false)}
                    >
                      Reject
                    </button>
                    {!canDecide && (
                      <span className="runbook__hint">
                        Enter your name to record a decision.
                      </span>
                    )}
                  </div>
                ) : (
                  <p className="runbook__decided">
                    {STATUS_LABELS[recommendation.status]} by{" "}
                    <strong>{recommendation.decided_by}</strong>
                    {recommendation.decision_note
                      ? ` — ${recommendation.decision_note}`
                      : ""}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </section>

    <BriefingPanel
      incidentId={incidentId}
      hasRecommendations={recommendations.length > 0}
    />
    </>
  );
}
