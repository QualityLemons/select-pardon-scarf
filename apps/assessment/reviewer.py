from .gold_standards import GOLD_STANDARDS


def generate_review(scoring_result):
    s      = scoring_result
    score  = s["score"]
    level  = s["level_key"]
    gs     = GOLD_STANDARDS.get(level, {})
    title  = gs.get("title", "PLC Challenge")
    role   = gs.get("role", "Automation Technician")
    grade  = s["grade"]
    eff    = s["efficiency_label"]
    done   = s["milestones_completed"]
    total  = s["milestones_total"]
    missed = [m for m in s["milestone_detail"] if not m["done"]]
    passed = [m for m in s["milestone_detail"] if m["done"]]

    if score >= 90:
        tier, tier_label = "exceptional", "Exceptional"
        p1 = (
            f"I am pleased to confirm an outstanding result on the {title} assessment. "
            f"The candidate achieved a score of {score}/100 (Grade {grade}), placing them "
            f"firmly in the top tier of technicians assessed at this level. "
            f"This performance reflects genuine competence in {_domain(level)} and "
            f"demonstrates the methodical, systematic thinking we expect of a {role}."
        )
        p3 = (
            f"On the basis of this result I am recommending the candidate for progression to the "
            f"next competency tier. They should now focus on applying these skills under live-plant "
            f"conditions and consider mentoring junior trainees through this same module. "
            f"I would expect them to attempt the subsequent challenge level within the next assessment cycle."
        )
    elif score >= 75:
        tier, tier_label = "proficient", "Proficient"
        p1 = (
            f"The candidate has passed the {title} assessment with a solid score of {score}/100 "
            f"(Grade {grade}). This is a competent performance demonstrating a good working "
            f"understanding of {_domain(level)}. "
            f"The result meets the standard required for the {role} designation, and I am "
            f"satisfied with the overall quality of the submission."
        )
        p3 = (
            f"I recommend the candidate addresses the minor gaps identified above before their "
            f"next assessment. Targeted practice on the missed criteria \u2014 particularly under "
            f"time pressure \u2014 will help consolidate understanding. "
            f"They are cleared to progress to the next challenge level but should revisit this "
            f"module's efficiency objectives in parallel."
        )
    elif score >= 60:
        tier, tier_label = "satisfactory", "Satisfactory"
        p1 = (
            f"The candidate has achieved a satisfactory result on the {title} assessment with a "
            f"score of {score}/100 (Grade {grade}). While they have demonstrated awareness of the "
            f"core concepts in {_domain(level)}, the submission shows areas where understanding "
            f"is not yet sufficiently consolidated for independent deployment as a {role}."
        )
        p3 = (
            f"Before attempting progression I would like the candidate to revisit the missed "
            f"criteria listed above and complete a supervised re-assessment within 30 days. "
            f"I strongly recommend working through the associated reference material and, where "
            f"possible, shadowing an experienced technician on live equipment. "
            f"A score of 75 or above on re-attempt will clear them for the next level."
        )
    elif score >= 45:
        tier, tier_label = "needs_improvement", "Needs Improvement"
        p1 = (
            f"Unfortunately the candidate has not met the required standard on the {title} "
            f"assessment. A score of {score}/100 (Grade {grade}) indicates significant gaps "
            f"in {_domain(level)} that must be addressed before the candidate can be considered "
            f"competent at the {role} level."
        )
        p3 = (
            f"I am placing a 60-day remedial development plan in effect. During this period "
            f"the candidate should: (1) complete the supplementary reading pack for this module; "
            f"(2) attend the relevant workshop if scheduled; and (3) complete a minimum of three "
            f"supervised practice sessions before the re-assessment. "
            f"Progression to the next level is suspended pending a passing re-attempt."
        )
    else:
        tier, tier_label = "unsatisfactory", "Unsatisfactory"
        p1 = (
            f"The candidate has not demonstrated the minimum competency required for the "
            f"{title} assessment, scoring {score}/100 (Grade {grade}). "
            f"This result indicates a fundamental gap in {_domain(level)} "
            f"and I cannot recommend this candidate for unsupervised work at the {role} level."
        )
        p3 = (
            f"I am referring this result to the Training Coordinator for an immediate review "
            f"of the candidate's development plan. A full re-induction of this module is "
            f"required before another assessment attempt is authorised. "
            f"The candidate must not progress to subsequent levels until a score of 60 or "
            f"above is achieved on this challenge."
        )

    p2 = _technical_paragraph(eff, done, total, passed, missed)

    return {
        "tier":        tier,
        "tier_label":  tier_label,
        "paragraph_1": p1,
        "paragraph_2": p2,
        "paragraph_3": p3,
        "summary_line": _summary(tier_label, score, grade, title),
    }


def _technical_paragraph(eff, done, total, passed, missed):
    parts = []
    pct = round(done / total * 100) if total else 0

    if done == total:
        parts.append(
            f"All {total} assessment milestones were completed successfully, "
            f"demonstrating full coverage of the scenario objectives."
        )
    elif done >= total * 0.8:
        parts.append(
            f"The candidate completed {done} of {total} milestones ({pct}%), "
            f"indicating strong but not complete coverage of the scenario objectives."
        )
    elif done >= total * 0.5:
        parts.append(
            f"The candidate completed {done} of {total} milestones ({pct}%), "
            f"showing partial understanding but leaving key objectives unverified."
        )
    else:
        parts.append(
            f"Only {done} of {total} milestones were completed ({pct}%), "
            f"which is below the minimum threshold for this assessment."
        )

    eff_map = {
        "Exceptional":
            "The solution was executed with exceptional efficiency \u2014 scan count was well within "
            "the optimal range, indicating confident, systematic operation.",
        "Proficient":
            "Operational efficiency was good; the candidate worked through the scenario "
            "in a reasonable number of scan cycles.",
        "Satisfactory":
            "The candidate took longer than the target number of scan cycles to complete the "
            "task, suggesting some hesitation or trial-and-error in their approach.",
        "Needs Improvement":
            "The scan cycle count was significantly above target, indicating a reactive rather "
            "than methodical approach to the task.",
        "Unsatisfactory":
            "The high scan cycle count suggests the candidate spent considerable time without "
            "purposeful progress, which would be unacceptable in a time-sensitive plant environment.",
    }
    parts.append(eff_map.get(eff, ""))

    if missed:
        labels = "; ".join(f'"{m["label"]}"' for m in missed[:3])
        suffix = f" and {len(missed)-3} further criteria" if len(missed) > 3 else ""
        parts.append(
            f"The following criteria were not met: {labels}{suffix}. "
            f"These represent gaps that must be addressed in follow-up training."
        )

    if passed:
        kws = ["latch", "safe", "fault", "timer", "state", "batch", "modbus", "reset", "drain", "fill"]
        key = [m["label"] for m in passed if any(k in m["label"].lower() for k in kws)]
        if not key:
            key = [m["label"] for m in passed[:2]]
        if key:
            parts.append(
                "Notably, the candidate correctly demonstrated: "
                + "; ".join(f'"{l}"' for l in key[:2])
                + " \u2014 core competencies that form the foundation of this qualification."
            )

    return " ".join(p for p in parts if p)


def _domain(level):
    return {
        "level1": "ladder logic and seal-in circuit design",
        "level2": "process control and fail-safe system design",
        "level3": "industrial Modbus TCP networking and protocol analysis",
        "level4": "functional safety interlock engineering (IEC 62061)",
        "level5": "PLC timer instructions and timed sequence control",
        "level6": "ISA-88 batch process state machine design",
    }.get(level, "PLC programming")


def _summary(tier_label, score, grade, title):
    return {
        "Exceptional":       f"Outstanding result \u2014 {score}/100 (Grade {grade}) on {title}.",
        "Proficient":        f"Competent pass \u2014 {score}/100 (Grade {grade}) on {title}.",
        "Satisfactory":      f"Satisfactory result \u2014 {score}/100 (Grade {grade}) on {title}. Targeted remediation advised.",
        "Needs Improvement": f"Below standard \u2014 {score}/100 (Grade {grade}) on {title}. Remedial plan required.",
        "Unsatisfactory":    f"Fail \u2014 {score}/100 (Grade {grade}) on {title}. Re-induction required.",
    }.get(tier_label, f"{score}/100 (Grade {grade})")
