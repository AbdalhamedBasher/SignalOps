import { useEffect, useState } from "react";

import {
  decideRecommendation,
  fetchRecommendations,
  requestRecommendations,
} from "../api/recommendations";
import type { AuthenticatedUser } from "../types/auth";
import type { Recommendation } from "../types/recommendation";
import { TriagePanel } from "./TriagePanel";

type RecommendationPanelProps = {
  incidentId: string;
  currentOperator: AuthenticatedUser | null;
};

const STATUS_LABELS: Record<Recommendation["status"], string> = {
  proposed: "awaiting review",
  approved: "approved",
  rejected: "rejected",
};

export function RecommendationPanel({
  incidentId,
  currentOperator,
}: RecommendationPanelProps) {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRetrieving, setIsRetrieving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
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

  const isSupervisor = currentOperator?.role === "supervisor";

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
            {/* WHY: Displays the authenticated operator responsible for the audit trail */}
            <div className="runbook__operator-badge">
              <span>Acting as:</span>
              <strong>{currentOperator?.display_name || "Authenticated Operator"}</strong>
              <span className={`role-tag role-tag--${currentOperator?.role || "engineer"}`}>
                {currentOperator?.role || "engineer"}
              </span>
            </div>

            <ol className="runbook__list">
              {recommendations.map((recommendation) => {
                const requiresSupervisor =
                  Boolean(recommendation.section.requires_supervisor);
                const canApprove =
                  !requiresSupervisor || isSupervisor;

                return (
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
                      {requiresSupervisor && (
                        <span className="supervisor-tag" title="High-risk procedure requiring supervisor approval">
                          Requires Supervisor
                        </span>
                      )}
                    </p>

                    <p className="runbook__rationale">
                      {recommendation.rationale}
                    </p>

                    <pre className="runbook__body">
                      {recommendation.section.body}
                    </pre>

                    {recommendation.status === "proposed" ? (
                      <div className="runbook__actions">
                        <button
                          className="runbook__approve"
                          type="button"
                          disabled={
                            !canApprove || pendingId === recommendation.id
                          }
                          onClick={() => void decide(recommendation, true)}
                          title={
                            requiresSupervisor && !isSupervisor
                              ? `Requires supervisor role. Switch to a supervisor to approve.`
                              : undefined
                          }
                        >
                          Approve
                        </button>
                        <button
                          className="runbook__reject"
                          type="button"
                          disabled={pendingId === recommendation.id}
                          onClick={() => void decide(recommendation, false)}
                        >
                          Reject
                        </button>
                        {requiresSupervisor && !isSupervisor && (
                          <span className="runbook__role-gate-hint">
                            ⚠️ Supervisor approval required ({currentOperator?.display_name} is {currentOperator?.role}).
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
                );
              })}
            </ol>
          </>
        )}
      </section>

      {/* WHY: TriagePanel places CAMARA network API orchestration and reasoning trace on screen */}
      <TriagePanel
        incidentId={incidentId}
        hasRecommendations={recommendations.length > 0}
      />
    </>
  );
}
