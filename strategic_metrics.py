"""Deployment-aligned metrics for strategic action gates.

The functions operate on already-produced decision predictions. They do not
train models and deliberately keep gate behavior separate from descriptive
policy/value metrics.
"""

import numpy as np

DEFAULT_THRESHOLDS = (0.0, 0.25, 0.5, 1.0, 2.0, 5.0)


def _finite(values):
    return np.asarray(values, dtype=np.float64)[np.isfinite(values)]


def gate_fire_curves(margins, thresholds=DEFAULT_THRESHOLDS):
    """Return opportunities, fires, and rates for each gate threshold."""
    m = _finite(margins)
    out = []
    for threshold in thresholds:
        fires = int(np.count_nonzero(m >= threshold))
        out.append({"threshold": float(threshold), "opportunities": int(len(m)),
                    "fires": fires,
                    "fire_rate": (fires / len(m)) if len(m) else None})
    return out


def _group_values(group, key):
    values = group.get(key, [])
    return np.asarray(values, dtype=np.float64)


def decision_advantage(group):
    """Return label/predicted candidate-minus-fallback advantage for a group."""
    model = int(group["model_idx"])
    fallback = int(group["fallback_idx"])
    label = _group_values(group, "label_q")
    pred = _group_values(group, "pred_q")
    if model < 0 or fallback < 0 or model >= len(label) or fallback >= len(label):
        return {"label": None, "predicted": None}
    return {"label": float(label[model] - label[fallback]),
            "predicted": (float(pred[model] - pred[fallback])
                          if model < len(pred) and fallback < len(pred) else None)}


def _summary(values):
    a = _finite(values)
    if not len(a):
        return {"n": 0, "mean": None, "median": None, "positive_fraction": None,
                "p05": None, "p25": None, "p75": None, "p95": None}
    return {"n": int(len(a)), "mean": float(a.mean()), "median": float(np.median(a)),
            "positive_fraction": float(np.mean(a > 0)),
            "p05": float(np.percentile(a, 5)), "p25": float(np.percentile(a, 25)),
            "p75": float(np.percentile(a, 75)), "p95": float(np.percentile(a, 95))}


def _correlation(x, y):
    x = _finite(x); y = _finite(y)
    if len(x) < 2 or len(x) != len(y) or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def analyze_decisions(groups, thresholds=DEFAULT_THRESHOLDS):
    """Analyze groups of candidate predictions and labels.

    Each group contains ``screen``, ``margin``, ``threshold``, ``fired``,
    ``model_idx``, ``fallback_idx``, ``best_idx``, ``pred_q`` and ``label_q``.
    Optional ``outcome`` is copied into override summaries when supplied.
    """
    groups = list(groups)
    margins = [g.get("margin", np.nan) for g in groups]
    result = {"opportunities": len(groups),
              "gate_fire_curves": gate_fire_curves(margins, thresholds),
              "overrides": {}, "advantage": {}, "regret": {}, "per_screen": {}}

    adv_all = []
    adv_fired = []
    pred_adv = []
    model_regret = []
    fallback_regret = []
    for g in groups:
        adv = decision_advantage(g)
        if adv["label"] is not None:
            adv_all.append(adv["label"])
            if g.get("fired", False): adv_fired.append(adv["label"])
        if adv["predicted"] is not None:
            pred_adv.append(adv["predicted"])
        label = _group_values(g, "label_q")
        if len(label):
            best = int(g.get("best_idx", int(np.argmax(label))))
            model = int(g["model_idx"])
            fallback = int(g["fallback_idx"])
            if 0 <= best < len(label):
                if 0 <= model < len(label): model_regret.append(label[best] - label[model])
                if 0 <= fallback < len(label): fallback_regret.append(label[best] - label[fallback])

        screen = str(g.get("screen", "all"))
        bucket = result["per_screen"].setdefault(screen, [])
        bucket.append(g)

    result["advantage"] = {"label_all": _summary(adv_all),
                            "label_fired": _summary(adv_fired),
                            "predicted": _summary(pred_adv),
                            "predicted_label_sign_accuracy": (
                                float(np.mean(np.sign(adv_all) == np.sign(pred_adv)))
                                if len(adv_all) == len(pred_adv) and adv_all else None),
                            "predicted_label_correlation": _correlation(pred_adv, adv_all)}
    result["regret"] = {"model": _summary(model_regret), "fallback": _summary(fallback_regret)}

    for screen, rows in list(result["per_screen"].items()):
        fired = [r for r in rows if r.get("fired", False)]
        result["per_screen"][screen] = _override_summary(rows, fired)
    result["overrides"] = _override_summary(groups, [g for g in groups if g.get("fired", False)])
    return result


def _override_summary(all_rows, fired_rows):
    overrides = [r for r in fired_rows if r.get("model_idx", -1) != r.get("fallback_idx", -1)]
    beneficial = harmful = neutral = 0
    for row in overrides:
        adv = decision_advantage(row)["label"]
        if adv is None: continue
        if adv > 0: beneficial += 1
        elif adv < 0: harmful += 1
        else: neutral += 1
    n = len(overrides)
    return {"opportunities": len(all_rows), "fires": len(fired_rows),
            "fire_rate": len(fired_rows) / len(all_rows) if all_rows else None,
            "overrides": n, "beneficial": beneficial, "harmful": harmful,
            "neutral": neutral,
            "beneficial_rate": beneficial / n if n else None,
            "harmful_rate": harmful / n if n else None,
            "neutral_rate": neutral / n if n else None}
