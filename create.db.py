"""
create_db.py — Creates and seeds plec.db (SQLite) from project data.
Run once: python create_db.py
Safe to re-run: drops and recreates all tables each time.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plec.db")

MODULES = [
    {
        "id":          "primer",
        "title":       "PLC Boot Camp",
        "type":        "lesson",
        "html_file":   "plc-primer.html",
        "difficulty":  0,
        "description": "25-term glossary, 6 learning tools, and 6 beginner video resources. Start here.",
        "role_title":  None,
        "sort_order":  0,
    },
    {
        "id":          "multimeter",
        "title":       "Digital Multimeter Tool",
        "type":        "tool",
        "html_file":   "multimeter.html",
        "difficulty":  1,
        "description": "Interactive DMM simulator with rotary dial, probe placement, and 4 fault-finding scenarios.",
        "role_title":  None,
        "sort_order":  1,
    },
    {
        "id":          "multimeter-lesson",
        "title":       "Multimeter Lesson",
        "type":        "lesson",
        "html_file":   "multimeter-lesson.html",
        "difficulty":  1,
        "description": "7-section lesson covering DMM anatomy, CAT ratings, measurement procedure, safety, and a quiz.",
        "role_title":  None,
        "sort_order":  2,
    },
    {
        "id":          "level1",
        "title":       "Start/Stop Latching Circuit",
        "type":        "challenge",
        "html_file":   "level1.html",
        "difficulty":  1,
        "description": "Seal-in latch, NC contacts, E-Stop fail-safe design, and the PLC scan cycle.",
        "role_title":  "Automation Technician – Tier 1",
        "sort_order":  3,
    },
    {
        "id":          "learn-your-log",
        "title":       "Learn Your Log",
        "type":        "lesson",
        "html_file":   "learn-your-log.html",
        "difficulty":  1,
        "description": "Why maintenance logs matter, 8 required fields, ISO 9001, and a spot-the-mistake exercise.",
        "role_title":  None,
        "sort_order":  4,
    },
    {
        "id":          "maintenance-log",
        "title":       "Maintenance Log Template",
        "type":        "tool",
        "html_file":   "maintenance-log.html",
        "difficulty":  1,
        "description": "Full structured log form: 8 sections, parts table, safety checklist, and print view.",
        "role_title":  None,
        "sort_order":  5,
    },
    {
        "id":          "level2",
        "title":       "Tank Filling System",
        "type":        "challenge",
        "html_file":   "level2.html",
        "difficulty":  2,
        "description": "Process control with NO/NC sensors, seal-in latch, hysteresis, and fail-safe fault injection.",
        "role_title":  "Process Control Technician – Tier 1",
        "sort_order":  6,
    },
    {
        "id":          "level3",
        "title":       "Modbus TCP Communication",
        "type":        "challenge",
        "html_file":   "level3.html",
        "difficulty":  3,
        "description": "MBAP header, function codes FC01/03/04/05/06/16, request builder, and protocol log.",
        "role_title":  "Industrial Networks Technician – Tier 2",
        "sort_order":  7,
    },
    {
        "id":          "level4",
        "title":       "Safety Interlock — Drill Machine",
        "type":        "challenge",
        "html_file":   "level4.html",
        "difficulty":  4,
        "description": "Dual-channel E-Stop, guard gate, RESET acknowledgement, IEC 62061, PSSR 2000.",
        "role_title":  "Functional Safety Engineer – IEC 62061",
        "sort_order":  8,
    },
    {
        "id":          "level5",
        "title":       "Timed Conveyor — TON Instruction",
        "type":        "challenge",
        "html_file":   "level5.html",
        "difficulty":  4,
        "description": "Timer On-Delay instruction, EN/TT/DN bits, preset vs accumulated value, mid-cycle E-Stop.",
        "role_title":  "Automation Technician – Tier 2",
        "sort_order":  9,
    },
    {
        "id":          "level6",
        "title":       "Sequential Batching — State Machine",
        "type":        "challenge",
        "html_file":   "level6.html",
        "difficulty":  5,
        "description": "ISA-88 state machine, mutual exclusion, IDLE/FILL/MIX/DRAIN states, auto-cycle.",
        "role_title":  "Process Automation Engineer – ISA-88",
        "sort_order":  10,
    },
]

MILESTONES = {
    "level1": [
        {"key": "m1", "label": "Observed START pulse (I0 momentary NO)",   "weight": 15, "order": 1},
        {"key": "m2", "label": "Motor latched ON after START released",     "weight": 25, "order": 2},
        {"key": "m3", "label": "Observed STOP NC contact opening",          "weight": 15, "order": 3},
        {"key": "m4", "label": "Motor dropped out on STOP",                 "weight": 25, "order": 4},
        {"key": "m5", "label": "Full start-run-stop cycle completed",       "weight": 20, "order": 5},
    ],
    "level2": [
        {"key": "m1", "label": "Pump started at low level (LS_LOW open)",    "weight": 20, "order": 1},
        {"key": "m2", "label": "Pump latched via seal circuit",               "weight": 20, "order": 2},
        {"key": "m3", "label": "Pump stopped at high level (LS_HIGH closed)", "weight": 20, "order": 3},
        {"key": "m4", "label": "Tank drained and auto-cycle restarted",       "weight": 20, "order": 4},
        {"key": "m5", "label": "All fault injection tests completed",         "weight": 20, "order": 5},
    ],
    "level3": [
        {"key": "m1", "label": "FC03 - Read holding registers",      "weight": 15, "order": 1},
        {"key": "m2", "label": "FC01 - Read coils",                  "weight": 10, "order": 2},
        {"key": "m3", "label": "FC05 - Write single coil",           "weight": 15, "order": 3},
        {"key": "m4", "label": "FC06 - Write single register",       "weight": 15, "order": 4},
        {"key": "m5", "label": "FC04 - Read input registers",        "weight": 10, "order": 5},
        {"key": "m6", "label": "FC16 - Write multiple registers",    "weight": 20, "order": 6},
        {"key": "m7", "label": "MBAP header inspected on 5+ frames", "weight": 15, "order": 7},
    ],
    "level4": [
        {"key": "m1", "label": "E-Stop tripped and drill stopped",           "weight": 15, "order": 1},
        {"key": "m2", "label": "Gate guard opened and drill stopped",        "weight": 15, "order": 2},
        {"key": "m3", "label": "RESET acknowledged after E-Stop",            "weight": 15, "order": 3},
        {"key": "m4", "label": "Dual-channel safety OK, drill running",      "weight": 20, "order": 4},
        {"key": "m5", "label": "E-Stop released mid-cycle",                  "weight": 10, "order": 5},
        {"key": "m6", "label": "Recovery: release E-Stop + RESET + START",  "weight": 15, "order": 6},
        {"key": "m7", "label": "Wire break fault - fail-safe shutdown",      "weight": 10, "order": 7},
    ],
    "level5": [
        {"key": "m1", "label": "First box detected and timer started",    "weight": 10, "order": 1},
        {"key": "m2", "label": "Conveyor ran for timed cycle",            "weight": 15, "order": 2},
        {"key": "m3", "label": "Timer DN bit fired",                      "weight": 15, "order": 3},
        {"key": "m4", "label": "E-Stop reset timer to zero mid-cycle",    "weight": 20, "order": 4},
        {"key": "m5", "label": "Timer preset modified and re-tested",     "weight": 15, "order": 5},
        {"key": "m6", "label": "Changed preset time and completed cycle", "weight": 15, "order": 6},
        {"key": "m7", "label": "5 boxes packed total",                    "weight": 10, "order": 7},
    ],
    "level6": [
        {"key": "m1", "label": "FILLING state entered (pump ON)",                    "weight": 15, "order": 1},
        {"key": "m2", "label": "MIXING state entered (agitator ON, timer started)",  "weight": 15, "order": 2},
        {"key": "m3", "label": "DRAINING state entered (drain valve open)",          "weight": 15, "order": 3},
        {"key": "m4", "label": "Full batch cycle completed (back to IDLE)",          "weight": 20, "order": 4},
        {"key": "m5", "label": "Mix timer elapsed correctly",                        "weight": 10, "order": 5},
        {"key": "m6", "label": "E-Stop abort tested mid-batch",                      "weight": 15, "order": 6},
        {"key": "m7", "label": "Auto-cycle completed 2+ batches",                   "weight": 10, "order": 7},
    ],
}

EFFICIENCY_THRESHOLDS = {
    "level1": {"exceptional": 300,  "proficient": 600,  "satisfactory": 1200, "poor": 2400},
    "level2": {"exceptional": 600,  "proficient": 1200, "satisfactory": 2400, "poor": 4800},
    "level3": {"exceptional": 20,   "proficient": 40,   "satisfactory": 80,   "poor": 160},
    "level4": {"exceptional": 500,  "proficient": 1000, "satisfactory": 2000, "poor": 4000},
    "level5": {"exceptional": 500,  "proficient": 1000, "satisfactory": 2000, "poor": 4000},
    "level6": {"exceptional": 800,  "proficient": 1600, "satisfactory": 3200, "poor": 6400},
}

BONUS_CRITERIA = {
    "level2": [{"key": "fault_tested", "label": "Fault injection tested",           "points": 5}],
    "level3": [{"key": "all_fc",       "label": "All 7 function codes used",        "points": 5}],
    "level4": [{"key": "wire_break",   "label": "Wire break fault simulated",       "points": 5}],
    "level5": [{"key": "estop_mid",    "label": "E-Stop tested mid-cycle",          "points": 5}],
    "level6": [
        {"key": "estop_abort", "label": "E-Stop abort mid-batch tested",   "points": 5},
        {"key": "autocycle",   "label": "Auto-cycle ran multiple batches", "points": 5},
    ],
}

SUPERVISOR_TIPS = {
    "multimeter": [
        {"order": 1, "icon": "🔌", "variant": "default", "text": "Always set the dial <strong>before</strong> connecting probes. Connecting probes on the wrong setting can damage the meter."},
        {"order": 2, "icon": "⚠️", "variant": "warn",    "text": "Red probe goes to the <strong>VΩmA</strong> socket. Black probe always goes to <strong>COM</strong>."},
        {"order": 3, "icon": "🔋", "variant": "good",    "text": "On DC voltage, a <em>negative</em> reading just means your probes are reversed — not a fault."},
        {"order": 4, "icon": "🛑", "variant": "danger",  "text": "Never measure resistance on a <strong>live circuit</strong>. Always isolate and lock off before using the Ω setting."},
        {"order": 5, "icon": "💡", "variant": "default", "text": "Continuity mode beeps when resistance is below ~30Ω. Useful for checking fuses and cable runs quickly."},
        {"order": 6, "icon": "📋", "variant": "purple",  "text": "CAT III meters are rated for distribution panels. CAT II is for household sockets. Always match the CAT rating to the installation."},
    ],
    "multimeter-lesson": [
        {"order": 1, "icon": "📖", "variant": "default", "text": "Work through each section in order — the quiz at the end draws on all five sections."},
        {"order": 2, "icon": "⚠️", "variant": "warn",    "text": "CAT ratings are not about voltage alone — they describe <strong>energy available</strong> in a fault. A higher CAT number means higher protection."},
        {"order": 3, "icon": "🔋", "variant": "good",    "text": "The three main measurements you will use daily: DC volts (24 V control circuits), AC volts (230 V supply check), continuity (cable and fuse test)."},
        {"order": 4, "icon": "💡", "variant": "default", "text": "Multimeters are the first tool a PLC engineer picks up on a fault call. Getting comfortable with one now saves time on the factory floor."},
        {"order": 5, "icon": "📋", "variant": "purple",  "text": "The quiz has 5 questions. You can retake it as many times as you like — there is no penalty for trying again."},
    ],
    "level1": [
        {"order": 1, "icon": "💡", "variant": "default", "text": "The seal-in contact (Q0) must be in <strong>parallel</strong> with the START button — not in series. That is what makes it a latch."},
        {"order": 2, "icon": "⚠️", "variant": "warn",    "text": "The STOP button uses a <strong>Normally Closed (NC)</strong> contact. At rest it passes power. Pressing STOP opens the circuit and drops the output."},
        {"order": 3, "icon": "🔁", "variant": "good",    "text": "Watch the scan cycle counter. The PLC evaluates every rung on every scan — even when nothing is changing."},
        {"order": 4, "icon": "🛑", "variant": "danger",  "text": "E-Stops must always be wired NC (fail-safe). If the wire breaks, the circuit opens and the machine stops — not the other way round."},
        {"order": 5, "icon": "📋", "variant": "purple",  "text": "Complete all five Challenge Milestones and then click <strong>Submit for Review</strong> to get your performance score."},
    ],
    "level2": [
        {"order": 1, "icon": "💡", "variant": "default", "text": "LS_LOW is a Normally Open (NO) float switch. When the tank is <em>low</em>, the float drops and the contact closes — starting the pump."},
        {"order": 2, "icon": "⚠️", "variant": "warn",    "text": "LS_HIGH is Normally Closed (NC) — wired fail-safe. If the sensor wire breaks, the contact opens and the pump stops. That is deliberate."},
        {"order": 3, "icon": "🔧", "variant": "default", "text": "The seal-in rung (Rung 2) keeps the pump running after LS_LOW rises back above the switch point. Without it, the pump would chatter on and off."},
        {"order": 4, "icon": "🛑", "variant": "danger",  "text": "Try the <strong>Fault Injection Lab</strong>: break LS_HIGH first, then LS_LOW. Observe how each failure mode behaves differently — one is safe, one is not."},
        {"order": 5, "icon": "📋", "variant": "purple",  "text": "Complete all five milestones including at least one fault injection test, then submit for your performance review."},
    ],
    "level3": [
        {"order": 1, "icon": "🌐", "variant": "default", "text": "Modbus TCP runs over standard Ethernet on <strong>port 502</strong>. The MBAP header wraps the classic Modbus PDU so it can travel over TCP/IP."},
        {"order": 2, "icon": "📦", "variant": "default", "text": "FC03 reads Holding Registers (outputs you can write). FC04 reads Input Registers (sensor values — read-only from the network side)."},
        {"order": 3, "icon": "⚠️", "variant": "warn",    "text": "Modbus register addresses start at <strong>0</strong> in the protocol, but some tools display them starting at 1. Always check which convention your device uses."},
        {"order": 4, "icon": "💡", "variant": "good",    "text": "The Transaction ID in the MBAP header lets a master match responses to requests when multiple requests are in flight at once."},
        {"order": 5, "icon": "📋", "variant": "purple",  "text": "Try all seven function codes and inspect at least 5 MBAP frames to unlock the full score. The protocol log shows every byte."},
    ],
    "level4": [
        {"order": 1, "icon": "🛑", "variant": "danger",  "text": "Safety circuits must use <strong>NC (Normally Closed)</strong> contacts for E-Stops and guards. A broken wire or loose connection makes the circuit open — and the machine stops."},
        {"order": 2, "icon": "⚠️", "variant": "warn",    "text": "Dual-channel safety means <em>two independent</em> signal paths are monitored. Both must be healthy before the machine can run."},
        {"order": 3, "icon": "💡", "variant": "default", "text": "After an E-Stop, you must press <strong>RESET</strong> before pressing START. This proves a human has assessed the situation — the machine does not restart automatically."},
        {"order": 4, "icon": "🔧", "variant": "default", "text": "IEC 62061 and PSSR 2000 are the UK standards for safety-related control systems. Knowing their names matters in a job interview."},
        {"order": 5, "icon": "📋", "variant": "purple",  "text": "Simulate the wire break fault (Channel 1 or 2) to see fail-safe behaviour in action. That milestone is worth 10 points in your review."},
    ],
    "level5": [
        {"order": 1, "icon": "⏱️", "variant": "default", "text": "The TON timer has three bits: <strong>EN</strong> (enable — rung is true), <strong>TT</strong> (timer timing — counting up), <strong>DN</strong> (done — accumulated ≥ preset)."},
        {"order": 2, "icon": "💡", "variant": "good",    "text": "When EN goes false, the accumulated value resets to zero. If you want a timer that <em>holds</em> its value, you need a RTO (Retentive Timer On) instead."},
        {"order": 3, "icon": "⚠️", "variant": "warn",    "text": "The DN bit stays true as long as EN is true and ACC ≥ PRE. It does not automatically reset — you need to unlatch or reset the rung to reuse it."},
        {"order": 4, "icon": "🔧", "variant": "default", "text": "Try pressing E-Stop while the timer is running. Watch what happens to the EN and TT bits — and check whether ACC resets."},
        {"order": 5, "icon": "📋", "variant": "purple",  "text": "Modify the preset value and run the cycle again. Changing timing is one of the most common commissioning adjustments on real conveyors."},
    ],
    "level6": [
        {"order": 1, "icon": "🔄", "variant": "default", "text": "A state machine can only be in <strong>one state at a time</strong>. That is the rule that prevents two outputs (e.g. fill valve and drain valve) from activating simultaneously."},
        {"order": 2, "icon": "💡", "variant": "good",    "text": "ISA-88 defines the standard states for batch processes: IDLE → FILLING → MIXING → DRAINING → IDLE. Real SCADA systems use this exact model."},
        {"order": 3, "icon": "⚠️", "variant": "warn",    "text": "The mix timer must elapse <em>inside</em> the MIXING state. If the state changes before the timer finishes, the timer resets — that is intentional."},
        {"order": 4, "icon": "🛑", "variant": "danger",  "text": "Press E-Stop mid-batch and observe: the state machine should jump to IDLE and all outputs should de-energise simultaneously."},
        {"order": 5, "icon": "📋", "variant": "purple",  "text": "Let the auto-cycle run at least two complete batches. The auto-cycle milestone and bonus points require observing the full IDLE → batch → IDLE → batch loop."},
    ],
    "learn-your-log": [
        {"order": 1, "icon": "📋", "variant": "default", "text": "A maintenance log is a <strong>legal document</strong> in most industrial settings. Under PSSR 2000 and PUWER 1998, records of inspection and repair must be kept and available for audit."},
        {"order": 2, "icon": "⚠️", "variant": "warn",    "text": "An incomplete log is almost as bad as no log. If a field is left blank, a future engineer or auditor has no way to know whether it was checked or simply forgotten."},
        {"order": 3, "icon": "💡", "variant": "good",    "text": "ISO 9001 requires that corrective actions are recorded and their effectiveness verified. A well-filled log is how you prove that happened."},
        {"order": 4, "icon": "🔧", "variant": "default", "text": "The eight required fields are: Date, Technician name, Equipment ID, Problem description, Faults found, Parts replaced, How the fix was verified, Supervisor sign-off."},
        {"order": 5, "icon": "📋", "variant": "purple",  "text": "The spot-the-mistake exercise uses real examples of poorly filled logs. These are based on common errors found during industrial audits."},
    ],
    "maintenance-log": [
        {"order": 1, "icon": "📋", "variant": "default", "text": "Fill in every field — including fields that do not apply. Write <em>N/A</em> rather than leaving them blank, so an auditor knows the field was considered."},
        {"order": 2, "icon": "⚠️", "variant": "warn",    "text": "The Job Number links this log to your work order system. Without it, tracing who did what and when becomes very difficult during an investigation."},
        {"order": 3, "icon": "💡", "variant": "good",    "text": "<strong>How was the fix demonstrated?</strong> — This is the most commonly skipped field. Running the machine and observing normal operation counts. Note what you observed."},
        {"order": 4, "icon": "🔧", "variant": "default", "text": "Parts replaced must include the part number if known. 'Replaced sensor' is less useful than 'Replaced Sick WT18-2P430 proximity sensor, serial 4492817'."},
        {"order": 5, "icon": "📋", "variant": "purple",  "text": "Use the Print button to produce a clean copy for your portfolio. Completed maintenance logs are useful evidence in an apprenticeship or job application."},
    ],
    "primer": [
        {"order": 1, "icon": "🚀", "variant": "default", "text": "Start with the glossary — filter by category (Hardware, Logic, Comms, Safety) to find terms relevant to whichever challenge you are working on."},
        {"order": 2, "icon": "💡", "variant": "good",    "text": "You do not need to memorise everything here before starting the challenges. Come back to the Boot Camp whenever you meet an unfamiliar term."},
        {"order": 3, "icon": "🎮", "variant": "default", "text": "The six alternative tools section includes Factory I/O, OpenPLC, and Codesys. These are used by industry professionals — PLeC is your on-ramp to all of them."},
        {"order": 4, "icon": "📺", "variant": "purple",  "text": "The video cards link to free YouTube content. Watching a real PLC being wired and programmed is a great complement to the browser-based simulations here."},
        {"order": 5, "icon": "⚠️", "variant": "warn",    "text": "PLC programming languages are standardised under <strong>IEC 61131-3</strong>. Ladder Logic (used throughout PLeC) is the most widely used language in UK manufacturing."},
    ],
}

GRADE_DESCRIPTORS = [
    {"grade": "A", "min_score": 90, "label": "Outstanding",         "description": "Exceptional performance. All milestones completed with high efficiency."},
    {"grade": "B", "min_score": 75, "label": "Proficient",          "description": "Strong performance. Most milestones completed with good efficiency."},
    {"grade": "C", "min_score": 60, "label": "Satisfactory",        "description": "Acceptable performance. Core milestones completed. Efficiency could improve."},
    {"grade": "D", "min_score": 45, "label": "Needs Improvement",   "description": "Partial completion. Review the challenge steps and try again."},
    {"grade": "F", "min_score": 0,  "label": "Incomplete",          "description": "Challenge not sufficiently completed. Work through all milestones before submitting."},
]


def build():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE modules (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            type        TEXT NOT NULL CHECK(type IN ('challenge','lesson','tool')),
            html_file   TEXT NOT NULL,
            difficulty  INTEGER NOT NULL DEFAULT 1,
            description TEXT,
            role_title  TEXT,
            sort_order  INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE milestones (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id   TEXT NOT NULL REFERENCES modules(id),
            milestone_key TEXT NOT NULL,
            label       TEXT NOT NULL,
            weight      INTEGER NOT NULL DEFAULT 10,
            sort_order  INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE efficiency_thresholds (
            module_id    TEXT PRIMARY KEY REFERENCES modules(id),
            exceptional  INTEGER NOT NULL,
            proficient   INTEGER NOT NULL,
            satisfactory INTEGER NOT NULL,
            poor         INTEGER NOT NULL
        );

        CREATE TABLE bonus_criteria (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id   TEXT NOT NULL REFERENCES modules(id),
            bonus_key   TEXT NOT NULL,
            label       TEXT NOT NULL,
            points      INTEGER NOT NULL DEFAULT 5
        );

        CREATE TABLE supervisor_tips (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id   TEXT NOT NULL REFERENCES modules(id),
            sort_order  INTEGER NOT NULL DEFAULT 0,
            icon        TEXT NOT NULL DEFAULT '💡',
            variant     TEXT NOT NULL DEFAULT 'default'
                        CHECK(variant IN ('default','warn','danger','good','purple')),
            tip_text    TEXT NOT NULL
        );

        CREATE TABLE grade_descriptors (
            grade       TEXT PRIMARY KEY,
            min_score   INTEGER NOT NULL,
            label       TEXT NOT NULL,
            description TEXT
        );
    """)

    cur.executemany(
        "INSERT INTO modules VALUES (:id,:title,:type,:html_file,:difficulty,:description,:role_title,:sort_order)",
        MODULES,
    )

    for module_id, rows in MILESTONES.items():
        cur.executemany(
            "INSERT INTO milestones (module_id,milestone_key,label,weight,sort_order) VALUES (?,?,?,?,?)",
            [(module_id, r["key"], r["label"], r["weight"], r["order"]) for r in rows],
        )

    for module_id, t in EFFICIENCY_THRESHOLDS.items():
        cur.execute(
            "INSERT INTO efficiency_thresholds VALUES (?,?,?,?,?)",
            (module_id, t["exceptional"], t["proficient"], t["satisfactory"], t["poor"]),
        )

    for module_id, rows in BONUS_CRITERIA.items():
        cur.executemany(
            "INSERT INTO bonus_criteria (module_id,bonus_key,label,points) VALUES (?,?,?,?)",
            [(module_id, r["key"], r["label"], r["points"]) for r in rows],
        )

    for module_id, rows in SUPERVISOR_TIPS.items():
        cur.executemany(
            "INSERT INTO supervisor_tips (module_id,sort_order,icon,variant,tip_text) VALUES (?,?,?,?,?)",
            [(module_id, r["order"], r["icon"], r["variant"], r["text"]) for r in rows],
        )

    cur.executemany(
        "INSERT INTO grade_descriptors VALUES (?,?,?,?)",
        [(r["grade"], r["min_score"], r["label"], r["description"]) for r in GRADE_DESCRIPTORS],
    )

    con.commit()
    con.close()

    size = os.path.getsize(DB_PATH)
    print(f"Created {DB_PATH} ({size:,} bytes)")

    # Print a quick summary
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    for table in ["modules", "milestones", "efficiency_thresholds", "bonus_criteria", "supervisor_tips", "grade_descriptors"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table:<25} {count:>3} rows")
    con.close()


if __name__ == "__main__":
    build()
