import json
import os
from datetime import datetime

ROOT = os.environ.get("BRAINLAB_ROOT", r"C:\AI_VAULT")

CAPITAL_STATE = os.path.join(ROOT, r"60_METRICS\capital_state.json")
DECISIONS_LOG = os.path.join(ROOT, r"50_LOGS\decisions\decisions.log")
FIN_LOG       = os.path.join(ROOT, r"50_LOGS\financial\financial.log")

def log_append(path: str, msg: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

def load_state():
    if not os.path.exists(CAPITAL_STATE):
        raise SystemExit(f"Missing capital_state.json: {CAPITAL_STATE}")
    with open(CAPITAL_STATE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(st):
    st["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(CAPITAL_STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)

def approve_commit(st, experiment_id: str, amount: float, reason: str):
    # Hard rules
    if amount <= 0:
        return False, "amount<=0"

    max_loss_abs = float(st.get("max_loss_abs", 0))
    max_per_exp  = float(st.get("max_per_experiment_abs", 0))
    max_total    = float(st.get("max_total_commit_abs", 0))

    current_cash = float(st.get("current_cash", 0))
    committed    = float(st.get("committed_cash", 0))
    realized_pnl = float(st.get("realized_pnl", 0))

    # Risk sanity
    if max_loss_abs <= 0 or max_per_exp <= 0 or max_total <= 0:
        return False, "risk_limits_invalid"

    # Per-experiment cap
    if amount > max_per_exp:
        return False, f"amount>{max_per_exp} (max_per_experiment_abs)"

    # Total commit cap
    if committed + amount > max_total:
        return False, f"committed+amount>{max_total} (max_total_commit_abs)"

    # Cash availability
    if amount > current_cash:
        return False, "insufficient_cash"

    # Global loss guard (realized)
    if realized_pnl < 0 and abs(realized_pnl) >= max_loss_abs:
        return False, f"global_loss_limit_reached abs(realized_pnl)>={max_loss_abs}"

    # Approve
    st["current_cash"]   = round(current_cash - amount, 2)
    st["committed_cash"] = round(committed + amount, 2)

    log_append(DECISIONS_LOG, f"APPROVE_COMMIT exp={experiment_id} amount={amount:.2f} reason={reason}")
    log_append(FIN_LOG, f"COMMIT exp={experiment_id} amount={amount:.2f} cash_now={st['current_cash']:.2f} committed_now={st['committed_cash']:.2f}")
    save_state(st)
    return True, "approved"

def release_commit(st, experiment_id: str, amount: float, pnl_realized: float, reason: str):
    current_cash = float(st.get("current_cash", 0))
    committed    = float(st.get("committed_cash", 0))
    realized_pnl = float(st.get("realized_pnl", 0))

    amount = max(0.0, float(amount))
    pnl_realized = float(pnl_realized)

    # Release back to cash
    st["committed_cash"] = round(max(0.0, committed - amount), 2)
    st["current_cash"]   = round(current_cash + amount + pnl_realized, 2)
    st["realized_pnl"]   = round(realized_pnl + pnl_realized, 2)

    log_append(DECISIONS_LOG, f"RELEASE exp={experiment_id} amount={amount:.2f} pnl={pnl_realized:.2f} reason={reason}")
    log_append(FIN_LOG, f"RELEASE exp={experiment_id} amount={amount:.2f} pnl={pnl_realized:.2f} cash_now={st['current_cash']:.2f} committed_now={st['committed_cash']:.2f} realized_pnl={st['realized_pnl']:.2f}")
    save_state(st)
    return True

def main():
    """
    MVP: command-driven allocator.
    Usage examples:
      python capital_allocator.py approve EXP-001 50 "test budget"
      python capital_allocator.py release EXP-001 50 12.5 "closed with profit"
    """
    import sys
    args = sys.argv[1:]
    if len(args) < 1:
        print("Usage:\n  approve <exp_id> <amount> <reason>\n  release <exp_id> <amount> <pnl> <reason>")
        raise SystemExit(2)

    cmd = args[0].lower()
    st = load_state()

    if cmd == "approve":
        if len(args) < 4:
            raise SystemExit("approve requires: exp_id amount reason")
        exp_id = args[1]
        amount = float(args[2])
        reason = " ".join(args[3:])
        ok, msg = approve_commit(st, exp_id, amount, reason)
        print(f"{'OK' if ok else 'NO'}: {msg}")
        return

    if cmd == "release":
        if len(args) < 5:
            raise SystemExit("release requires: exp_id amount pnl reason")
        exp_id = args[1]
        amount = float(args[2])
        pnl    = float(args[3])
        reason = " ".join(args[4:])
        release_commit(st, exp_id, amount, pnl, reason)
        print("OK: released")
        return

    raise SystemExit(f"Unknown cmd: {cmd}")

if __name__ == "__main__":
    main()