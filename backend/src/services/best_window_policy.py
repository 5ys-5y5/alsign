"""Best Window policy helpers and safe formula evaluation."""

import math
from typing import Any, Dict, Optional

from ..database.queries import policies as policy_queries

BEST_WINDOW_POLICY_ENDPOINT = "eventsHistory"
BEST_WINDOW_POLICY_FUNCTION = "eventsHistory_bestWindow"

DEFAULT_BEST_WINDOW_POLICY: Dict[str, Any] = {
    "offsets": {
        "start": -14,
        "end": 14,
    },
    "designated": {
        "totalReturnFormula": "mean_value",
        "avgFormula": "math.log(1 + total_return) / hold",
        "avgAfterFeeFormula": "(total_return - fee_rate) / hold",
        "topK": 2,
    },
    "previous": {
        "totalReturnFormula": "compound_return",
        "avgFormula": "math.log(1 + total_return) / length",
        "avgAfterFeeFormula": "(total_return - fee_rate) / length",
        "topK": 2,
    },
    "backtest": {
        "atr": {
            "period": 14,
            "method": "wilder",
        },
        "exit": {
            "mode": "percent",
            "stopLossAtr": 1.0,
            "takeProfitAtr": 2.0,
        },
        "risk": {
            "lambda": 1.0,
        },
        "strategy": {
            "dailyReturnMode": "spread",
            "annualizationDays": 252,
        },
    },
}


def merge_best_window_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(policy, dict):
        policy = {}
    offsets = policy.get("offsets", {}) if isinstance(policy.get("offsets"), dict) else {}
    merged = {
        "offsets": {
            "start": offsets.get("start", DEFAULT_BEST_WINDOW_POLICY["offsets"]["start"]),
            "end": offsets.get("end", DEFAULT_BEST_WINDOW_POLICY["offsets"]["end"]),
        },
        "designated": _merge_mode_policy(policy.get("designated"), DEFAULT_BEST_WINDOW_POLICY["designated"]),
        "previous": _merge_mode_policy(policy.get("previous"), DEFAULT_BEST_WINDOW_POLICY["previous"]),
        "backtest": _merge_backtest_policy(policy.get("backtest")),
    }
    return merged


def _merge_mode_policy(mode_policy: Optional[Dict[str, Any]], defaults: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(mode_policy, dict):
        mode_policy = {}
    merged = {
        "totalReturnFormula": mode_policy.get("totalReturnFormula", defaults["totalReturnFormula"]),
        "avgFormula": mode_policy.get("avgFormula", defaults["avgFormula"]),
        "avgAfterFeeFormula": mode_policy.get("avgAfterFeeFormula", defaults["avgAfterFeeFormula"]),
        "topK": int(mode_policy.get("topK", defaults.get("topK", 2)) or defaults.get("topK", 2)),
    }
    return merged


def _merge_backtest_policy(backtest_policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(backtest_policy, dict):
        backtest_policy = {}
    atr_policy = backtest_policy.get("atr", {}) if isinstance(backtest_policy.get("atr"), dict) else {}
    exit_policy = backtest_policy.get("exit", {}) if isinstance(backtest_policy.get("exit"), dict) else {}
    risk_policy = backtest_policy.get("risk", {}) if isinstance(backtest_policy.get("risk"), dict) else {}
    strategy_policy = backtest_policy.get("strategy", {}) if isinstance(backtest_policy.get("strategy"), dict) else {}
    return {
        "atr": {
            "period": int(atr_policy.get("period", DEFAULT_BEST_WINDOW_POLICY["backtest"]["atr"]["period"])),
            "method": atr_policy.get("method", DEFAULT_BEST_WINDOW_POLICY["backtest"]["atr"]["method"]),
        },
        "exit": {
            "mode": exit_policy.get("mode", DEFAULT_BEST_WINDOW_POLICY["backtest"]["exit"]["mode"]),
            "stopLossAtr": float(exit_policy.get("stopLossAtr", DEFAULT_BEST_WINDOW_POLICY["backtest"]["exit"]["stopLossAtr"])),
            "takeProfitAtr": float(exit_policy.get("takeProfitAtr", DEFAULT_BEST_WINDOW_POLICY["backtest"]["exit"]["takeProfitAtr"])),
        },
        "risk": {
            "lambda": float(risk_policy.get("lambda", DEFAULT_BEST_WINDOW_POLICY["backtest"]["risk"]["lambda"])),
        },
        "strategy": {
            "dailyReturnMode": strategy_policy.get(
                "dailyReturnMode",
                DEFAULT_BEST_WINDOW_POLICY["backtest"]["strategy"]["dailyReturnMode"],
            ),
            "annualizationDays": int(strategy_policy.get(
                "annualizationDays",
                DEFAULT_BEST_WINDOW_POLICY["backtest"]["strategy"]["annualizationDays"],
            )),
        },
    }


def evaluate_best_window_formula(expression: Optional[str], context: Dict[str, Any]) -> Optional[float]:
    if not expression:
        return None
    safe_namespace = {
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "len": len,
        "round": round,
        "float": float,
        "int": int,
        "math": math,
    }
    safe_namespace.update(context)
    try:
        return eval(expression, {"__builtins__": {}}, safe_namespace)
    except Exception:
        return None


def get_best_window_offsets(policy: Dict[str, Any]) -> Dict[str, Any]:
    offsets = policy.get("offsets", {}) if isinstance(policy, dict) else {}
    offset_start = int(offsets.get("start", DEFAULT_BEST_WINDOW_POLICY["offsets"]["start"]))
    offset_end = int(offsets.get("end", DEFAULT_BEST_WINDOW_POLICY["offsets"]["end"]))
    offset_start = max(-14, min(14, offset_start))
    offset_end = max(-14, min(14, offset_end))
    if offset_start > offset_end:
        offset_start, offset_end = -14, 14
    return {
        "start": offset_start,
        "end": offset_end,
        "offsets": list(range(offset_start, offset_end + 1)),
    }


async def load_best_window_policy(pool) -> Dict[str, Any]:
    policy_row = await policy_queries.select_policy(pool, BEST_WINDOW_POLICY_FUNCTION)
    policy = policy_row["policy"] if policy_row else None
    return merge_best_window_policy(policy)
