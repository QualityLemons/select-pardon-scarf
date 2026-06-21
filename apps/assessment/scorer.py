from .gold_standards import GOLD_STANDARDS


def score_attempt(level_key, milestones_done, scan_count, elapsed_ms, bonus_flags=None):
    gs = GOLD_STANDARDS.get(level_key)
    if not gs:
        return _unknown(level_key)

    bonus_flags = bonus_flags or {}
    done_set    = set(milestones_done)

    total_w  = sum(m["weight"] for m in gs["milestones"])
    earned_w = sum(m["weight"] for m in gs["milestones"] if m["id"] in done_set)
    milestone_score = round((earned_w / total_w) * 80) if total_w else 0

    milestone_detail = [
        {"id": m["id"], "label": m["label"], "weight": m["weight"], "done": m["id"] in done_set}
        for m in gs["milestones"]
    ]

    thr = gs["efficiency_thresholds"]
    if   scan_count <= thr["exceptional"]:  eff_score, eff_label = 15, "Exceptional"
    elif scan_count <= thr["proficient"]:   eff_score, eff_label = 11, "Proficient"
    elif scan_count <= thr["satisfactory"]: eff_score, eff_label = 7,  "Satisfactory"
    elif scan_count <= thr["poor"]:         eff_score, eff_label = 3,  "Needs Improvement"
    else:                                   eff_score, eff_label = 0,  "Unsatisfactory"

    bonus_score  = 0
    bonus_detail = []
    for bc in gs.get("bonus_criteria", []):
        earned = bool(bonus_flags.get(bc["key"]))
        if earned:
            bonus_score += bc["points"]
        bonus_detail.append({"label": bc["label"], "earned": earned, "points": bc["points"]})
    bonus_score = min(bonus_score, 5)

    score = min(milestone_score + eff_score + bonus_score, 100)

    return {
        "level_key":            level_key,
        "score":                score,
        "grade":                _grade(score),
        "milestone_score":      milestone_score,
        "efficiency_score":     eff_score,
        "bonus_score":          bonus_score,
        "efficiency_label":     eff_label,
        "milestone_detail":     milestone_detail,
        "bonus_detail":         bonus_detail,
        "milestones_completed": len(done_set & {m["id"] for m in gs["milestones"]}),
        "milestones_total":     len(gs["milestones"]),
        "scan_count":           scan_count,
        "elapsed_ms":           elapsed_ms,
    }


def _grade(s):
    if s >= 90: return "A"
    if s >= 75: return "B"
    if s >= 60: return "C"
    if s >= 45: return "D"
    return "F"


def _unknown(level_key):
    return {
        "level_key": level_key, "score": 0, "grade": "F",
        "milestone_score": 0, "efficiency_score": 0, "bonus_score": 0,
        "efficiency_label": "Unknown", "milestone_detail": [], "bonus_detail": [],
        "milestones_completed": 0, "milestones_total": 0,
        "scan_count": 0, "elapsed_ms": 0,
    }
