"""
algorithms.py  ·  v2
====================
AI algorithms for the Disaster Response Planner.

CHANGES FROM v1
───────────────
• Corrected heuristic formula (v1 mixed CSP scoring into A* — made it
  inadmissible and produced sub-optimal paths):
    urgency_score = distance
                  + (SEVERITY_WEIGHT × severity)
                  + (HOSPITAL_LOAD_WEIGHT × hospital_load × 10)
  A* now uses plain admissible Manhattan distance as h(n).

• DecisionReport dataclass: structured explanation returned to UI for
  rich rendering instead of a plain string.

• find_best_ambulance(): chooses the nearest idle ambulance per incident.

• debug_log(): respects DEBUG_MODE flag — print step-by-step AI reasoning.

• USER_BLOCK (5): new cell type for user-placed roadblocks; treated as
  impassable by A* so dynamic replanning routes around them.

• csp_assign(): unchanged contract but now logs scores when DEBUG_MODE=True.

Cell type constants (shared with simulation.py / ui.py)
────────────────────────────────────────────────────────
  ROAD=0  BLOCK=1  HOSPITAL=2  INCIDENT=3  DISASTER_ZONE=4  USER_BLOCK=5
"""

import heapq
import math
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

# ── Debug mode ────────────────────────────────────────────────────────────────
DEBUG_MODE: bool = False   # flip True for verbose console output


def debug_log(msg: str) -> None:
    if DEBUG_MODE:
        print(f"[AI DEBUG]  {msg}")


# ── Cell type constants ───────────────────────────────────────────────────────
ROAD          = 0
BLOCK         = 1
HOSPITAL      = 2
INCIDENT      = 3
DISASTER_ZONE = 4
USER_BLOCK    = 5   # user-placed road-block; impassable

# Movement cost per cell type
COST: Dict[int, float] = {
    ROAD:          1.0,
    DISASTER_ZONE: 3.0,   # costly → A* prefers safer detours
    HOSPITAL:      1.0,
    INCIDENT:      1.5,   # slightly costly to traverse an incident cell
    USER_BLOCK:    math.inf,
}

IMPASSABLE = {BLOCK, USER_BLOCK}

# ── Heuristic weights (tunable constants) ─────────────────────────────────────
SEVERITY_WEIGHT:      float = 1.5
HOSPITAL_LOAD_WEIGHT: float = 2.0

DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]   # 4-directional grid


# ─────────────────────────────────────────────────────────────────────────────
# DECISION REPORT  (replaces plain-string explain_heuristic)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DecisionReport:
    """
    Structured record of one AI dispatch decision.
    UI renders .full() in the decision panel and .short() in the demo bar.
    """
    ambulance_id:      int
    incident_id:       int
    hospital_id:       int
    severity:          int
    distance_cells:    int
    hospital_load_pct: int
    heuristic_score:   float
    path_length:       int
    reason:            str
    score_breakdown:   str

    def short(self) -> str:
        return (
            f"Unit {self.ambulance_id} → Incident #{self.incident_id} "
            f"[sev {self.severity}/10]  →  Hospital #{self.hospital_id} "
            f"({self.hospital_load_pct}% full)  path={self.path_length} cells"
        )

    def full(self) -> str:
        bar = "━" * 28
        return (
            f"{bar}\n"
            f"  AMBULANCE  : Unit {self.ambulance_id}\n"
            f"  INCIDENT   : #{self.incident_id}  (severity {self.severity}/10)\n"
            f"  HOSPITAL   : #{self.hospital_id}  ({self.hospital_load_pct}% load)\n"
            f"  DISTANCE   : {self.distance_cells} cells\n"
            f"  PATH LEN   : {self.path_length} steps\n"
            f"  SCORE      : {self.heuristic_score:.2f}\n"
            f"  FORMULA    : {self.score_breakdown}\n"
            f"  REASON     : {self.reason}\n"
            f"{bar}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# HEURISTIC / SCORING FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def manhattan(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    """Admissible Manhattan distance — used as A* h(n)."""
    return float(abs(a[0] - b[0]) + abs(a[1] - b[1]))


def urgency_score(
    pos: Tuple[int, int],
    goal: Tuple[int, int],
    severity: int,
    hospital_load: float,
) -> float:
    """
    Combined urgency score for CSP hospital assignment.

    Formula (v2):
      score = distance
            + (SEVERITY_WEIGHT × severity)
            + (HOSPITAL_LOAD_WEIGHT × hospital_load × 10)

    Interpretation:
      • Distance term: nearer hospitals get lower base score.
      • Severity term: higher severity raises score → dispatched first
        when incidents are sorted by DESCENDING score in the priority queue.
      • Load term: busier hospitals are less attractive.

    This is NOT injected into A* (doing so would break admissibility).
    """
    dist      = manhattan(pos, goal)
    sev_term  = SEVERITY_WEIGHT * severity
    load_term = HOSPITAL_LOAD_WEIGHT * hospital_load * 10
    score     = dist + sev_term + load_term
    debug_log(
        f"urgency_score {pos}→{goal} "
        f"dist={dist:.1f} + sev_term={sev_term:.1f} + load_term={load_term:.1f} "
        f"= {score:.2f}"
    )
    return score


# ─────────────────────────────────────────────────────────────────────────────
# A* SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def a_star(
    grid: List[List[int]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
    severity: int = 5,
    hospital_load: float = 0.5,
) -> Optional[List[Tuple[int, int]]]:
    """
    A* shortest-path search on a weighted 2-D grid.

    Heuristic: admissible Manhattan distance.
    Edge costs: defined in COST dict (DISASTER_ZONE = 3×, USER_BLOCK = ∞).

    severity / hospital_load parameters kept for backward compatibility
    but are no longer used inside A* (they belong to CSP scoring).

    Returns list of (row, col) from start to goal inclusive, or None.
    """
    rows, cols = len(grid), len(grid[0])

    # Each heap entry: (f_cost, g_cost, (row, col))
    open_heap: List[Tuple[float, float, Tuple[int, int]]] = []
    heapq.heappush(open_heap, (manhattan(start, goal), 0.0, start))

    came_from: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start: None}
    g_score:   Dict[Tuple[int, int], float]                     = {start: 0.0}

    while open_heap:
        _, g, current = heapq.heappop(open_heap)

        if current == goal:
            path = _reconstruct_path(came_from, current)
            debug_log(f"A* path found  {start}→{goal}  {len(path)} steps")
            return path

        # Skip stale heap entries
        if g > g_score.get(current, math.inf):
            continue

        r, c = current
        for dr, dc in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            cell = grid[nr][nc]
            if cell in IMPASSABLE:
                continue

            step_cost = COST.get(cell, 1.0)
            new_g     = g + step_cost
            neighbour = (nr, nc)

            if new_g < g_score.get(neighbour, math.inf):
                g_score[neighbour] = new_g
                f = new_g + manhattan(neighbour, goal)
                heapq.heappush(open_heap, (f, new_g, neighbour))
                came_from[neighbour] = current

    debug_log(f"A* no path found  {start}→{goal}")
    return None


def _reconstruct_path(
    came_from: Dict[Tuple[int, int], Optional[Tuple[int, int]]],
    current:   Tuple[int, int],
) -> List[Tuple[int, int]]:
    path = []
    while current is not None:
        path.append(current)
        current = came_from[current]
    path.reverse()
    return path


# ─────────────────────────────────────────────────────────────────────────────
# CSP — ASSIGN INCIDENTS TO HOSPITALS
# ─────────────────────────────────────────────────────────────────────────────

def csp_assign(
    incidents: List[Dict],
    hospitals: List[Dict],
    grid: List[List[int]],   # kept for API compat; could be used for path costs
) -> Dict[int, int]:
    """
    Greedy CSP solver.

    Variables   : one per active incident → hospital assignment
    Domain      : hospitals with remaining capacity > 0
    Constraints : capacity limit per hospital
    Ordering    : incidents sorted by descending severity (most urgent first)
    Evaluation  : urgency_score() — lower score wins

    Returns  dict  incident_id → hospital_id
    """
    active = sorted(
        [i for i in incidents if i.get('active', True)],
        key=lambda x: -x['severity'],
    )

    # Track remaining slots per hospital
    remaining: Dict[int, int] = {
        h['id']: max(0, h['capacity'] - h['current_load'])
        for h in hospitals
    }

    assignment: Dict[int, int] = {}

    for inc in active:
        best_hid   = None
        best_score = math.inf

        for hosp in hospitals:
            hid = hosp['id']
            if remaining.get(hid, 0) <= 0:
                continue   # capacity constraint

            load  = hosp['current_load'] / max(hosp['capacity'], 1)
            score = urgency_score(
                inc['pos'], hosp['pos'], inc['severity'], load
            )

            if score < best_score:
                best_score = score
                best_hid   = hid

        if best_hid is not None:
            assignment[inc['id']] = best_hid
            remaining[best_hid]  -= 1
            debug_log(
                f"CSP  inc#{inc['id']} sev={inc['severity']} → "
                f"hosp#{best_hid}  score={best_score:.2f}"
            )

    return assignment


# ─────────────────────────────────────────────────────────────────────────────
# BEST AMBULANCE SELECTOR
# ─────────────────────────────────────────────────────────────────────────────

def find_best_ambulance(
    incident: Dict,
    idle_ambulances: List[Dict],
) -> Optional[int]:
    """
    Select the nearest idle ambulance for the given incident.
    Returns ambulance id or None if no idle units exist.
    """
    best_id    = None
    best_dist  = math.inf

    for amb in idle_ambulances:
        d = manhattan(amb['pos'], incident['pos'])
        if d < best_dist:
            best_dist = d
            best_id   = amb['id']

    debug_log(
        f"Best ambulance for inc#{incident['id']}: "
        f"unit#{best_id}  dist={best_dist:.0f}"
    )
    return best_id


# ─────────────────────────────────────────────────────────────────────────────
# DECISION REPORT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_decision_report(
    ambulance_id: int,
    incident: Dict,
    hospital: Dict,
    path: List,
) -> DecisionReport:
    """Construct a full DecisionReport for one dispatch action."""
    dist      = int(manhattan(incident['pos'], hospital['pos']))
    load_frac = hospital['current_load'] / max(hospital['capacity'], 1)
    load_pct  = int(load_frac * 100)
    score     = urgency_score(
        incident['pos'], hospital['pos'], incident['severity'], load_frac
    )

    breakdown = (
        f"{dist} (dist) "
        f"+ {SEVERITY_WEIGHT}×{incident['severity']} (sev) "
        f"+ {HOSPITAL_LOAD_WEIGHT}×{load_frac:.2f}×10 (load) "
        f"= {score:.2f}"
    )

    # Human-readable reason
    sev = incident['severity']
    if sev >= 8:
        prefix = "⚠ CRITICAL — "
    elif sev >= 5:
        prefix = "⚡ URGENT — "
    else:
        prefix = ""

    if load_pct < 60:
        reason = f"{prefix}nearest hospital with low occupancy ({load_pct}%)"
    elif load_pct < 85:
        reason = f"{prefix}nearest available; moderate load ({load_pct}%)"
    else:
        reason = f"{prefix}only hospital with remaining capacity ({load_pct}%)"

    return DecisionReport(
        ambulance_id      = ambulance_id,
        incident_id       = incident['id'],
        hospital_id       = hospital['id'],
        severity          = sev,
        distance_cells    = dist,
        hospital_load_pct = load_pct,
        heuristic_score   = score,
        path_length       = len(path),
        reason            = reason,
        score_breakdown   = breakdown,
    )


# ── Backward-compat shim ──────────────────────────────────────────────────────
def explain_heuristic(
    ambulance_id: int,
    incident:     Dict,
    hospital:     Dict,
    path_length:  int,
) -> str:
    """Legacy wrapper — returns DecisionReport.full() as a string."""
    fake_path = [None] * path_length
    report = build_decision_report(ambulance_id, incident, hospital, fake_path)   # type: ignore
    return report.full()
