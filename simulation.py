"""
simulation.py  ·  v2
====================
City grid, entities and simulation loop.

CHANGES FROM v1
───────────────
• USER_BLOCK support: toggle_block(row,col) marks/unmarks a road cell as
  USER_BLOCK, then triggers full replan so every affected ambulance reroutes.

• add_incident(row, col): user can place a new incident anywhere on a road cell.

• increase_severity(): now also selects a better ambulance if a closer idle
  unit exists — uses find_best_ambulance() from algorithms.py.

• Dynamic replanning: _replan_all() re-runs CSP + A* for EVERY active
  ambulance whenever the grid changes (roadblock added, severity raised, new
  incident spawned).  Previously only idle ambulances were re-dispatched.

• Metrics: completed_missions, avg_response_time, efficiency_pct tracked live.

• DecisionReport: dispatch_all() stores the latest report on each Ambulance
  instance as .decision so the UI can render a rich decision card.

• _maybe_spawn_incident(): spawns only on non-DISASTER_ZONE cells to avoid
  cluttering the danger zone with too many incidents at once.

• Simulation.step() supports sub-tick interpolation via path_progress (0.0–1.0)
  for smooth animation in the UI.
"""

import random
import time
import math
from typing import List, Dict, Optional, Tuple

from algorithms import (
    ROAD, BLOCK, HOSPITAL, INCIDENT, DISASTER_ZONE, USER_BLOCK,
    a_star, csp_assign, find_best_ambulance,
    build_decision_report, DecisionReport,
    debug_log,
)

GRID_SIZE = 21

# Cells that ambulances and incidents can use as road
PASSABLE_ROAD = {ROAD, DISASTER_ZONE, INCIDENT}

# Street rows/cols — every 3rd index is a road (matches the city-grid image)
STREET_LINES = {0, 3, 6, 9, 12, 15, 18, 20}


def _is_road(r: int, c: int) -> bool:
    return (r in STREET_LINES) or (c in STREET_LINES)


def _make_base_grid() -> List[List[int]]:
    return [
        [ROAD if _is_road(r, c) else BLOCK for c in range(GRID_SIZE)]
        for r in range(GRID_SIZE)
    ]


# ── Fixed layout (mirrors the reference image) ────────────────────────────────

HOSPITAL_POSITIONS: List[Tuple[int, int]] = [
    (0, 6),    # top-left   "Central"
    (6, 12),   # upper-mid  "Hospital"
    (12, 18),  # right
    (15, 6),   # lower-left
    (9,  9),   # centre
]

INITIAL_INCIDENTS = [
    {'id': 1, 'pos': (3,  9),  'severity': 7},
    {'id': 2, 'pos': (6,  6),  'severity': 5},
    {'id': 3, 'pos': (9, 12),  'severity': 8},
    {'id': 4, 'pos': (12, 9),  'severity': 4},
    {'id': 5, 'pos': (15, 15), 'severity': 6},
    {'id': 6, 'pos': (18, 12), 'severity': 3},
    {'id': 7, 'pos': (18, 6),  'severity': 9},
]

INITIAL_AMBULANCES = [
    {'id': 1, 'pos': (0,  3)},
    {'id': 2, 'pos': (3,  0)},
    {'id': 3, 'pos': (0, 18)},
    {'id': 4, 'pos': (9,  0)},
    {'id': 5, 'pos': (18, 0)},
]

# Disaster zone rectangles  (r0, c0, r1, c1) inclusive
DISASTER_RECTS = [
    (0, 6,  9, 15),
    (6, 9, 15, 18),
]


# ─────────────────────────────────────────────────────────────────────────────
# ENTITIES
# ─────────────────────────────────────────────────────────────────────────────

class Ambulance:
    """
    Represents one ambulance unit.

    path_progress (0.0–1.0) tracks smooth interpolation between the last cell
    and the next cell so the UI can draw the van at a fractional position.
    """

    def __init__(self, aid: int, pos: Tuple[int, int]):
        self.id    = aid
        self.pos   = pos           # current grid cell (row, col)
        self.prev_pos = pos        # previous cell — for smooth interpolation

        self.path:        List[Tuple[int, int]] = []
        self.path_index:  int   = 0
        self.path_progress: float = 1.0   # 0.0 = just left prev_pos, 1.0 = arrived

        self.target_incident: Optional[int] = None
        self.target_hospital: Optional[int] = None
        # States: idle | en_route_incident | en_route_hospital | selected
        self.state      = 'idle'
        self.last_update = time.time()

        # AI decision attached at dispatch time
        self.decision:  Optional[DecisionReport] = None
        self.highlighted: bool = False   # UI highlight flag

    @property
    def display_time(self) -> str:
        t = time.localtime(self.last_update)
        h = t.tm_hour
        suffix = 'AM' if h < 12 else 'PM'
        h12 = h % 12 or 12
        return f"{h12:02d}:{t.tm_min:02d} {suffix}"

    def to_dict(self) -> Dict:
        return {'id': self.id, 'pos': self.pos}


class Incident:
    def __init__(self, iid: int, pos: Tuple[int, int], severity: int):
        self.id        = iid
        self.pos       = pos
        self.severity  = severity   # 1–10
        self.active    = True
        self.assigned  = False
        self.timestamp = time.time()

    @property
    def display_time(self) -> str:
        t = time.localtime(self.timestamp)
        h = t.tm_hour
        suffix = 'AM' if h < 12 else 'PM'
        h12 = h % 12 or 12
        return f"{h12:02d}:{t.tm_min:02d} {suffix}"

    def to_dict(self) -> Dict:
        return {
            'id':       self.id,
            'pos':      self.pos,
            'severity': self.severity,
            'active':   self.active,
        }


class Hospital:
    def __init__(self, hid: int, pos: Tuple[int, int]):
        self.id           = hid
        self.pos          = pos
        self.capacity     = random.randint(12, 20)
        self.current_load = random.randint(4, 10)

    @property
    def load_fraction(self) -> float:
        return self.current_load / max(self.capacity, 1)

    def to_dict(self) -> Dict:
        return {
            'id':           self.id,
            'pos':          self.pos,
            'capacity':     self.capacity,
            'current_load': self.current_load,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

class Simulation:
    """
    Central state machine.  UI calls step() each tick; simulation notifies
    registered callbacks after every state change.
    """

    def __init__(self):
        self.grid:       List[List[int]] = _make_base_grid()
        self.ambulances: List[Ambulance] = []
        self.incidents:  List[Incident]  = []
        self.hospitals:  List[Hospital]  = []

        # ── Live metrics ────────────────────────────────────────────────────
        self.lives_saved:        int         = 1_346_300_000
        self.completed_missions: int         = 0
        self.response_times:     List[float] = []
        self.efficiency_pct:     float       = 100.0

        # ── Control state ───────────────────────────────────────────────────
        self.running:      bool  = False
        self.speed:        float = 1.0
        self.demo_mode:    bool  = False
        self.demo_message: str   = ''

        # Most recent AI decision for the decision panel
        self.latest_decision: Optional[DecisionReport] = None

        # Interaction mode for map clicks: 'incident' | 'block' | 'severity'
        self.click_mode: str = 'severity'

        self._tick_callbacks: list = []
        self._init_entities()

    # ── Initialisation ───────────────────────────────────────────────────────

    def _init_entities(self):
        # Apply disaster zones
        for r0, c0, r1, c1 in DISASTER_RECTS:
            for r in range(r0, min(r1 + 1, GRID_SIZE)):
                for c in range(c0, min(c1 + 1, GRID_SIZE)):
                    if self.grid[r][c] == ROAD:
                        self.grid[r][c] = DISASTER_ZONE

        # Hospitals
        for i, pos in enumerate(HOSPITAL_POSITIONS):
            h = Hospital(i + 1, pos)
            self.hospitals.append(h)
            self.grid[pos[0]][pos[1]] = HOSPITAL

        # Incidents
        for d in INITIAL_INCIDENTS:
            inc = Incident(d['id'], d['pos'], d['severity'])
            self.incidents.append(inc)
            r, c = d['pos']
            if self.grid[r][c] not in (BLOCK, HOSPITAL):
                self.grid[r][c] = INCIDENT

        # Ambulances
        for d in INITIAL_AMBULANCES:
            self.ambulances.append(Ambulance(d['id'], d['pos']))

    def reset(self):
        self.ambulances.clear()
        self.incidents.clear()
        self.hospitals.clear()
        self.lives_saved        = 1_346_300_000
        self.completed_missions = 0
        self.response_times     = []
        self.efficiency_pct     = 100.0
        self.demo_message       = ''
        self.latest_decision    = None
        self.grid               = _make_base_grid()
        self._init_entities()

    # ── Callbacks ────────────────────────────────────────────────────────────

    def register_tick_callback(self, fn):
        self._tick_callbacks.append(fn)

    def _notify(self):
        for fn in self._tick_callbacks:
            fn()

    # ── Map interaction ──────────────────────────────────────────────────────

    def toggle_block(self, row: int, col: int):
        """
        Toggle a road cell between ROAD / DISASTER_ZONE and USER_BLOCK.
        Hospitals and existing incidents cannot be blocked.
        Triggers full AI replan so ambulances reroute around new obstacles.
        """
        cell = self.grid[row][col]
        if cell in (HOSPITAL, BLOCK):
            return   # never block fixed structures

        if cell == USER_BLOCK:
            # Unblock — restore to ROAD
            self.grid[row][col] = ROAD
            self.demo_message = f"🔓 Road ({row},{col}) unblocked — AI replanning…"
        elif cell in (ROAD, DISASTER_ZONE):
            self.grid[row][col] = USER_BLOCK
            self.demo_message = f"🚧 Road ({row},{col}) blocked — AI replanning…"
        else:
            return   # don't block incident cells

        # Invalidate all active ambulance paths — they must reroute
        for amb in self.ambulances:
            if amb.state != 'idle':
                amb.path       = []
                amb.path_index = 0
                amb.state      = 'idle'
        self._replan_all()
        self._notify()

    def add_incident(self, row: int, col: int):
        """
        Add a user-placed incident at the clicked road cell.
        Severity defaults to 5 (medium); user can click again to increase it.
        """
        cell = self.grid[row][col]
        if cell not in (ROAD, DISASTER_ZONE):
            return   # only allow incidents on roads

        new_id  = max((i.id for i in self.incidents), default=0) + 1
        severity = 5
        inc = Incident(new_id, (row, col), severity)
        self.incidents.append(inc)
        self.grid[row][col] = INCIDENT
        self.demo_message = f"📍 New incident #{new_id} added at ({row},{col})"
        debug_log(f"User-added incident #{new_id} at ({row},{col})")
        self._replan_all()
        self._notify()

    def increase_severity(self, incident_id: int):
        """
        Increase severity of an incident by +1 (max 10).
        Re-evaluates best ambulance and reruns A* for that incident.
        """
        for inc in self.incidents:
            if inc.id == incident_id and inc.active:
                old_sev     = inc.severity
                inc.severity = min(10, inc.severity + 1)

                # Release any ambulance already assigned so it can be
                # reassigned if a closer/better unit is available
                for amb in self.ambulances:
                    if amb.target_incident == incident_id:
                        amb.path         = []
                        amb.path_index   = 0
                        amb.state        = 'idle'
                        amb.highlighted  = False

                self.demo_message = (
                    f"⚡ Incident #{incident_id} severity "
                    f"{old_sev}→{inc.severity}/10  AI rerouting…"
                )
                debug_log(
                    f"Severity increased inc#{incident_id}: {old_sev}→{inc.severity}"
                )
                self._replan_all()
                break

    # ── AI dispatch ──────────────────────────────────────────────────────────

    def _replan_all(self):
        """
        Full replan: re-run CSP + A* for ALL active unresolved incidents.
        Called on every grid change (roadblock, severity increase, new incident).
        """
        # Mark all assigned incidents as unassigned so they can be reassigned
        for inc in self.incidents:
            if inc.active:
                inc.assigned = False

        # Release all ambulances that no longer have a valid path
        for amb in self.ambulances:
            if amb.state != 'idle' and (not amb.path or amb.path_index >= len(amb.path)):
                amb.state      = 'idle'
                amb.path       = []
                amb.path_index = 0

        self.dispatch_all()

    def dispatch_all(self):
        """
        Run CSP to assign incidents to hospitals.
        Use find_best_ambulance() to select the optimal idle unit per incident.
        Run A* for each assignment and activate the ambulance.
        """
        inc_dicts  = [i.to_dict() for i in self.incidents if i.active]
        hosp_dicts = [h.to_dict() for h in self.hospitals]

        # CSP: incident → hospital mapping
        assignment = csp_assign(inc_dicts, hosp_dicts, self.grid)

        # Collect unassigned active incidents sorted by severity (most urgent first)
        unassigned = sorted(
            [i for i in self.incidents if i.active and not i.assigned],
            key=lambda x: -x.severity,
        )

        idle_dicts = [a.to_dict() for a in self.ambulances if a.state == 'idle']

        for inc in unassigned:
            if not idle_dicts:
                break   # no free ambulances

            hosp_id = assignment.get(inc.id)
            if hosp_id is None:
                continue

            hospital = next((h for h in self.hospitals if h.id == hosp_id), None)
            if hospital is None:
                continue

            # Pick nearest idle ambulance for this incident
            best_amb_id = find_best_ambulance(inc.to_dict(), idle_dicts)
            if best_amb_id is None:
                continue

            amb = next((a for a in self.ambulances if a.id == best_amb_id), None)
            if amb is None:
                continue

            path = a_star(
                self.grid, amb.pos, inc.pos,
                severity=inc.severity,
                hospital_load=hospital.load_fraction,
            )

            if not path:
                debug_log(f"No path for unit#{amb.id} → inc#{inc.id}")
                continue

            # Build and store structured decision report
            report = build_decision_report(
                amb.id, inc.to_dict(), hospital.to_dict(), path
            )
            amb.decision         = report
            amb.path             = path
            amb.path_index       = 1
            amb.prev_pos         = amb.pos
            amb.path_progress    = 0.0
            amb.target_incident  = inc.id
            amb.target_hospital  = hosp_id
            amb.state            = 'en_route_incident'
            amb.highlighted      = True
            amb.last_update      = time.time()
            inc.assigned         = True

            self.latest_decision = report
            self.demo_message    = report.short()

            debug_log(f"Dispatched unit#{amb.id} → inc#{inc.id} via hosp#{hosp_id}")

            # Remove this ambulance from the idle pool for this dispatch round
            idle_dicts = [d for d in idle_dicts if d['id'] != amb.id]

    # ── Simulation step ──────────────────────────────────────────────────────

    def step(self):
        """
        Advance simulation by one tick.
        Each ambulance moves one cell along its A* path.
        path_progress is set to 0.0 on move start so UI can animate smoothly.
        """
        for amb in self.ambulances:
            if amb.state == 'idle' or not amb.path:
                continue

            if amb.path_index < len(amb.path):
                amb.prev_pos      = amb.pos
                amb.pos           = amb.path[amb.path_index]
                amb.path_index   += 1
                amb.path_progress = 0.0   # UI animates 0→1 between ticks
                amb.last_update   = time.time()
            else:
                # Arrived at waypoint
                if amb.state == 'en_route_incident':
                    self._arrive_at_incident(amb)
                elif amb.state == 'en_route_hospital':
                    self._arrive_at_hospital(amb)

        self._notify()

    def _arrive_at_incident(self, amb: Ambulance):
        inc = self._get_incident(amb.target_incident)
        if inc is None:
            amb.state = 'idle'; amb.path = []; return

        hospital = self._get_hospital(amb.target_hospital)
        if hospital is None:
            amb.state = 'idle'; amb.path = []; return

        path = a_star(
            self.grid, amb.pos, hospital.pos,
            severity=inc.severity,
            hospital_load=hospital.load_fraction,
        )
        if path:
            amb.path          = path
            amb.path_index    = 1
            amb.path_progress = 0.0
            amb.state         = 'en_route_hospital'
            self.demo_message = (
                f"🏥 Unit {amb.id} picked up Incident #{inc.id} "
                f"→ heading to Hospital #{hospital.id}"
            )
        else:
            amb.state = 'idle'; amb.path = []

    def _arrive_at_hospital(self, amb: Ambulance):
        inc      = self._get_incident(amb.target_incident)
        hospital = self._get_hospital(amb.target_hospital)

        if inc:
            # Mark incident resolved; clean up grid cell
            inc.active   = False
            inc.assigned = False
            r, c = inc.pos
            if self.grid[r][c] == INCIDENT:
                self.grid[r][c] = ROAD

        if hospital:
            hospital.current_load = min(
                hospital.capacity, hospital.current_load + 1
            )

        # Update metrics
        elapsed = time.time() - (inc.timestamp if inc else time.time())
        self.response_times.append(max(1.0, elapsed))
        self.lives_saved        += random.randint(1, 5)
        self.completed_missions += 1
        self._update_efficiency()

        # Release ambulance
        amb.state            = 'idle'
        amb.path             = []
        amb.path_index       = 0
        amb.path_progress    = 1.0
        amb.target_incident  = None
        amb.target_hospital  = None
        amb.highlighted      = False

        self.demo_message = (
            f"✅ Unit {amb.id} delivered patient to Hospital #{hospital.id if hospital else '?'}  "
            f"| Missions: {self.completed_missions}"
        )
        debug_log(f"Mission complete unit#{amb.id}  missions={self.completed_missions}")

        # Keep simulation alive with new incidents
        self._maybe_spawn_incident()
        self.dispatch_all()

    def _update_efficiency(self):
        """
        Efficiency = (completed missions / total incidents ever created) × 100.
        Penalised slightly if average response time is high.
        """
        total = max(1, len(self.incidents))
        base  = (self.completed_missions / total) * 100
        if self.response_times:
            avg_rt = sum(self.response_times) / len(self.response_times)
            # Ideal response time ~30 s; deduct up to 20 pts for slow response
            rt_penalty = min(20, max(0, (avg_rt - 30) / 10))
            self.efficiency_pct = max(0, min(100, base - rt_penalty))
        else:
            self.efficiency_pct = base

    def _maybe_spawn_incident(self):
        """Spawn a new incident on a normal road cell (not disaster zone)."""
        road_cells = [
            (r, c)
            for r in range(GRID_SIZE)
            for c in range(GRID_SIZE)
            if self.grid[r][c] == ROAD   # prefer safe road cells
        ]
        if not road_cells:
            road_cells = [
                (r, c)
                for r in range(GRID_SIZE)
                for c in range(GRID_SIZE)
                if self.grid[r][c] == DISASTER_ZONE
            ]
        if not road_cells:
            return

        pos    = random.choice(road_cells)
        new_id = max((i.id for i in self.incidents), default=0) + 1
        inc    = Incident(new_id, pos, random.randint(2, 9))
        self.incidents.append(inc)
        self.grid[pos[0]][pos[1]] = INCIDENT
        debug_log(f"Spawned incident #{new_id} at {pos} sev={inc.severity}")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_incident(self, iid: Optional[int]) -> Optional[Incident]:
        if iid is None: return None
        return next((i for i in self.incidents if i.id == iid), None)

    def _get_hospital(self, hid: Optional[int]) -> Optional[Hospital]:
        if hid is None: return None
        return next((h for h in self.hospitals if h.id == hid), None)

    def incident_at(self, row: int, col: int) -> Optional[Incident]:
        """Return active incident at (row, col), or None."""
        return next(
            (i for i in self.incidents if i.active and i.pos == (row, col)),
            None,
        )

    def is_user_block(self, row: int, col: int) -> bool:
        return self.grid[row][col] == USER_BLOCK

    def active_incidents(self) -> List[Incident]:
        return [i for i in self.incidents if i.active]

    def avg_response_time(self) -> float:
        if not self.response_times: return 0.0
        return sum(self.response_times) / len(self.response_times)
