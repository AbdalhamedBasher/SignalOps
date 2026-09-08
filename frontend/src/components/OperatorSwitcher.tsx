import { DEMO_OPERATORS, type AuthenticatedUser } from "../types/auth";
import { switchOperator } from "../api/auth";

type OperatorSwitcherProps = {
  currentOperator: AuthenticatedUser | null;
  onOperatorChange: (operator: AuthenticatedUser) => void;
};

export function OperatorSwitcher({
  currentOperator,
  onOperatorChange,
}: OperatorSwitcherProps) {
  async function handleSelect(username: string) {
    if (currentOperator?.username === username) return;
    try {
      const auth = await switchOperator(username);
      onOperatorChange(auth.user);
    } catch (err) {
      console.error("Failed to switch operator", err);
    }
  }

  return (
    <div className="operator-switcher" aria-label="Demo operator profile">
      <span className="operator-switcher__label">Operator:</span>
      <div className="operator-switcher__pills">
        {DEMO_OPERATORS.map((op) => {
          const isActive = currentOperator?.username === op.username;
          return (
            <button
              key={op.username}
              type="button"
              className={`operator-pill ${
                isActive ? "operator-pill--active" : ""
              } operator-pill--${op.role}`}
              onClick={() => void handleSelect(op.username)}
              title={`Switch session to ${op.name} (${op.badge})`}
            >
              <span className="operator-pill__dot" aria-hidden="true" />
              <span className="operator-pill__name">{op.name}</span>
              <span className="operator-pill__badge">{op.badge}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
