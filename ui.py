"""
ui.py  ·  v2
============
Dashboard UI — upgraded Tkinter canvas application.

CHANGES FROM v1
───────────────
• Smooth ambulance animation: path_progress interpolated 0→1 between ticks
  via a _smooth_tick() that runs at 30 fps independently of the sim tick rate.
• Decision Panel (right side): renders DecisionReport.full() with colour-coded
  severity / load indicators — replaces the plain demo_message label.
• Map click modes: user switches between "Add Incident", "Block Road",
  "Increase Severity" via a toolbar — clearly labelled.
• Metrics bar (right panel): lives saved, missions completed, avg response
  time, efficiency % — all update in real-time.
• Selected/highlighted ambulance pulsing outline on the map.
• Demo Mode button: auto-runs a narrated scenario (AI decisions visible).
• Speed buttons: Slow (0.5×) / Normal (1×) / Fast (3×) — replaces slider for
  cleaner UX (slider still exists for fine-grained control).
• User-placed roadblocks rendered as orange diagonal-hatched cells.
• Path rendering: each ambulance path drawn in a unique colour tint.
• Hospital load bars drawn directly on the hospital circle on the map.
• Incident triangles scale with severity (bigger = more critical).
• Debug toggle in the header bar (prints AI logs to console).
"""

import tkinter as tk
from tkinter import ttk
import math
import random
import time
from typing import List, Optional, Tuple

from simulation import Simulation, GRID_SIZE
from algorithms import (
    ROAD, BLOCK, HOSPITAL, INCIDENT, DISASTER_ZONE, USER_BLOCK,
    DEBUG_MODE, debug_log,
)
import algorithms   # so we can flip algorithms.DEBUG_MODE at runtime

# ── Colour palette ────────────────────────────────────────────────────────────
BG_DARK       = '#0d1117'
BG_PANEL      = '#161b22'
BG_CARD       = '#1c2128'
BG_HEADER     = '#0d1117'
BG_SEP        = '#21262d'

ACCENT_BLUE   = '#388bfd'
ACCENT_GREEN  = '#3fb950'
ACCENT_RED    = '#f85149'
ACCENT_YELLOW = '#d29922'
ACCENT_ORANGE = '#e3663e'
ACCENT_PURPLE = '#bc8cff'
ACCENT_TEAL   = '#39d353'
WHITE         = '#e6edf3'
GREY          = '#8b949e'
DARK_GREY     = '#30363d'

# Map colours
MAP_ROAD        = '#1a2332'
MAP_BLOCK       = '#0d1117'
MAP_DISASTER    = '#3d1212'
MAP_HOSPITAL_BG = '#0f3460'
MAP_INCIDENT_BG = '#3d2800'
MAP_PATH_BASE   = '#3fb950'
MAP_GRID_LINE   = '#1c2128'
MAP_USER_BLOCK  = '#4a2800'

# Path colours per ambulance id (up to 5)
PATH_COLORS = ['#3fb950', '#388bfd', '#bc8cff', '#39d353', '#e3663e']

CELL_PX = 27   # pixels per grid cell

# Ambulance icon size
AMB_W, AMB_H = 10, 7


# ─────────────────────────────────────────────────────────────────────────────
# CHART WIDGETS
# ─────────────────────────────────────────────────────────────────────────────

class BarChart:
    """
    Reusable bar chart drawn on a shared Canvas at a fixed offset.
    Supports multi-color bars via a colors list.
    """

    def __init__(self, canvas: tk.Canvas, x: int, y: int,
                 w: int, h: int, labels: List[str],
                 colors: Optional[List[str]] = None):
        self.canvas = canvas
        self.x, self.y, self.w, self.h = x, y, w, h
        self.labels = labels
        self.colors = colors or [ACCENT_BLUE] * len(labels)
        self.values: List[float] = [0.0] * len(labels)
        self._tag = f'bar_{id(self)}'

    def update(self, values: List[float]):
        self.values = list(values)
        self._draw()

    def _draw(self):
        c = self.canvas
        c.delete(self._tag)
        n = len(self.values)
        if n == 0:
            return
        bar_w   = max(4, (self.w - 12) // n - 3)
        max_v   = max(self.values) if any(v > 0 for v in self.values) else 1
        chart_h = self.h - 16

        for i, v in enumerate(self.values):
            bh  = max(2, int((v / max_v) * chart_h))
            bx  = self.x + 6 + i * (bar_w + 3)
            by  = self.y + chart_h - bh
            col = self.colors[i % len(self.colors)]
            # Bar body
            c.create_rectangle(
                bx, by, bx + bar_w, self.y + chart_h,
                fill=col, outline='', tags=self._tag
            )
            # Highlight cap
            c.create_rectangle(
                bx, by, bx + bar_w, by + 2,
                fill='white', outline='', tags=self._tag
            )
            # Label
            if i < len(self.labels):
                c.create_text(
                    bx + bar_w // 2, self.y + chart_h + 8,
                    text=self.labels[i], fill=GREY,
                    font=('Consolas', 7), tags=self._tag
                )
            # Value text
            if v > 0:
                c.create_text(
                    bx + bar_w // 2, by - 8,
                    text=str(int(v)), fill=WHITE,
                    font=('Consolas', 7), tags=self._tag
                )


class LineChart:
    """Sparkline chart with gradient fill below the line."""

    def __init__(self, canvas: tk.Canvas, x: int, y: int,
                 w: int, h: int, color: str, max_pts: int = 20):
        self.canvas  = canvas
        self.x, self.y, self.w, self.h = x, y, w, h
        self.color   = color
        self.max_pts = max_pts
        self.values: List[float] = []
        self._tag    = f'line_{id(self)}'

    def add(self, v: float):
        self.values.append(v)
        if len(self.values) > self.max_pts:
            self.values.pop(0)
        self._draw()

    def set_all(self, values: List[float]):
        self.values = list(values[-self.max_pts:])
        self._draw()

    def _draw(self):
        c = self.canvas
        c.delete(self._tag)
        n = len(self.values)
        if n < 2:
            return
        min_v = min(self.values)
        max_v = max(self.values)
        rng   = max_v - min_v or 1
        inner = self.h - 4

        def pt(i: int) -> Tuple[int, int]:
            px_ = self.x + int(i / (n - 1) * self.w)
            py_ = self.y + inner - int((self.values[i] - min_v) / rng * inner) + 2
            return px_, py_

        pts = [pt(i) for i in range(n)]

        # Draw line segments
        for i in range(n - 1):
            c.create_line(
                pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                fill=self.color, width=2, tags=self._tag
            )

        # Dot at latest point
        lx, ly = pts[-1]
        c.create_oval(lx-3, ly-3, lx+3, ly+3,
                      fill=self.color, outline='', tags=self._tag)

        # Value label
        c.create_text(lx + 6, ly, text=f"{self.values[-1]:.0f}s",
                      fill=self.color, font=('Consolas', 7),
                      anchor='w', tags=self._tag)


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD APP
# ─────────────────────────────────────────────────────────────────────────────

class DashboardApp:

    def __init__(self, sim: Simulation):
        self.sim = sim
        sim.register_tick_callback(self._on_sim_tick)

        self.root = tk.Tk()
        self.root.title("AI DISASTER RESPONSE PLANNER  ·  v2")
        self.root.configure(bg=BG_DARK)
        self.root.geometry("1260x730")
        self.root.resizable(False, False)

        # Animation state
        self._smooth_progress: dict = {}   # amb.id → progress float 0→1
        self._smooth_running = False

        self._build_layout()
        self._draw_map()
        sim.dispatch_all()
        self._start_smooth_loop()

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT CONSTRUCTION
    # ─────────────────────────────────────────────────────────────────────────

    def _build_layout(self):
        # ── Header bar ───────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG_HEADER, height=34)
        hdr.pack(fill='x', side='top')
        hdr.pack_propagate(False)

        tk.Label(
            hdr, text="≡  AI DISASTER RESPONSE PLANNER  —  DASHBOARD",
            bg=BG_HEADER, fg=WHITE, font=('Consolas', 11, 'bold')
        ).pack(side='left', padx=12, pady=6)

        # Debug toggle
        self._debug_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            hdr, text='DEBUG', variable=self._debug_var,
            bg=BG_HEADER, fg=GREY, selectcolor=BG_CARD,
            activebackground=BG_HEADER, font=('Consolas', 8),
            command=self._toggle_debug
        ).pack(side='right', padx=8)

        self._lbl_time = tk.Label(hdr, text='', bg=BG_HEADER, fg=GREY,
                                  font=('Consolas', 10))
        self._lbl_time.pack(side='right', padx=12)
        self._update_clock()

        # ── 3-column content ─────────────────────────────────────────────
        content = tk.Frame(self.root, bg=BG_DARK)
        content.pack(fill='both', expand=True, padx=4, pady=4)

        # Left panel (controls + unit/incident lists)
        left = tk.Frame(content, bg=BG_PANEL, width=215)
        left.pack(side='left', fill='y', padx=(0, 3))
        left.pack_propagate(False)
        self._build_left_panel(left)

        # Centre (map + toolbar)
        centre = tk.Frame(content, bg=BG_DARK)
        centre.pack(side='left', fill='both', expand=True, padx=(0, 3))
        self._build_centre(centre)

        # Right panel (metrics + charts + decision)
        right = tk.Frame(content, bg=BG_PANEL, width=232)
        right.pack(side='right', fill='y')
        right.pack_propagate(False)
        self._build_right_panel(right)

    # ── LEFT PANEL ────────────────────────────────────────────────────────

    def _build_left_panel(self, parent):
        # ── Start / Pause / Reset ────────────────────────────────────────
        btn_frame = tk.Frame(parent, bg=BG_PANEL)
        btn_frame.pack(fill='x', padx=6, pady=(8, 0))

        bcfg = dict(font=('Consolas', 8, 'bold'), relief='flat',
                    pady=5, cursor='hand2', bd=0)

        self._btn_start = tk.Button(
            btn_frame, text='▶ START', bg=ACCENT_GREEN, fg=BG_DARK,
            command=self._on_start, **bcfg)
        self._btn_start.pack(side='left', fill='x', expand=True, padx=(0, 2))

        self._btn_pause = tk.Button(
            btn_frame, text='⏸ PAUSE', bg=ACCENT_YELLOW, fg=BG_DARK,
            command=self._on_pause, **bcfg)
        self._btn_pause.pack(side='left', fill='x', expand=True, padx=(0, 2))

        self._btn_reset = tk.Button(
            btn_frame, text='↺ RESET', bg=DARK_GREY, fg=WHITE,
            command=self._on_reset, **bcfg)
        self._btn_reset.pack(side='left', fill='x', expand=True)

        # ── Speed buttons ─────────────────────────────────────────────────
        spd_frame = tk.Frame(parent, bg=BG_PANEL)
        spd_frame.pack(fill='x', padx=6, pady=(5, 0))
        tk.Label(spd_frame, text='Speed:', bg=BG_PANEL, fg=GREY,
                 font=('Consolas', 8)).pack(side='left')
        for label, val in [('Slow', 0.5), ('Normal', 1.0), ('Fast', 3.0)]:
            tk.Button(
                spd_frame, text=label, bg=BG_CARD, fg=WHITE,
                font=('Consolas', 7), relief='flat', padx=4, pady=2,
                cursor='hand2', bd=0,
                command=lambda v=val: self._set_speed(v)
            ).pack(side='left', padx=2)

        # Fine slider
        self._speed_var = tk.DoubleVar(value=1.0)
        tk.Scale(
            parent, from_=0.25, to=5.0, resolution=0.25,
            orient='horizontal', variable=self._speed_var,
            bg=BG_PANEL, fg=WHITE, troughcolor=DARK_GREY,
            highlightthickness=0, bd=0, showvalue=True,
            length=195, font=('Consolas', 7),
            command=lambda v: setattr(self.sim, 'speed', float(v))
        ).pack(fill='x', padx=6, pady=(2, 4))

        # ── Demo mode button ──────────────────────────────────────────────
        tk.Button(
            parent, text='🎬  DEMO MODE', bg='#1e3a5f', fg=ACCENT_BLUE,
            font=('Consolas', 8, 'bold'), relief='flat', pady=4,
            cursor='hand2', bd=0, command=self._on_demo
        ).pack(fill='x', padx=6, pady=(0, 6))

        # ── Active Units ──────────────────────────────────────────────────
        self._section_hdr(parent, '  Active Units  ▲')
        self._units_frame = tk.Frame(parent, bg=BG_PANEL)
        self._units_frame.pack(fill='x')

        # ── Incidents ─────────────────────────────────────────────────────
        self._section_hdr(parent, '  Incidents  ▲')

        inc_scroll = tk.Frame(parent, bg=BG_PANEL)
        inc_scroll.pack(fill='both', expand=True)
        self._incidents_frame = tk.Frame(inc_scroll, bg=BG_PANEL)
        self._incidents_frame.pack(fill='x')

    def _section_hdr(self, parent, text):
        f = tk.Frame(parent, bg=BG_SEP)
        f.pack(fill='x', pady=(4, 0))
        tk.Label(f, text=text, bg=BG_SEP, fg=WHITE,
                 font=('Consolas', 9, 'bold'), pady=3
                 ).pack(side='left', padx=6)

    # ── CENTRE ────────────────────────────────────────────────────────────

    def _build_centre(self, parent):
        # Interaction toolbar
        toolbar = tk.Frame(parent, bg=BG_CARD, height=30)
        toolbar.pack(fill='x', pady=(0, 3))
        toolbar.pack_propagate(False)

        tk.Label(toolbar, text='Map mode:', bg=BG_CARD, fg=GREY,
                 font=('Consolas', 8)).pack(side='left', padx=8, pady=5)

        self._click_mode_var = tk.StringVar(value='severity')
        modes = [
            ('⚡ Severity+', 'severity', ACCENT_YELLOW),
            ('📍 Add Incident', 'incident', ACCENT_RED),
            ('🚧 Block Road', 'block', ACCENT_ORANGE),
        ]
        for label, mode, color in modes:
            tk.Radiobutton(
                toolbar, text=label, variable=self._click_mode_var, value=mode,
                bg=BG_CARD, fg=color, selectcolor=BG_DARK,
                activebackground=BG_CARD, font=('Consolas', 8),
                indicatoron=True, cursor='hand2',
                command=lambda m=mode: setattr(self.sim, 'click_mode', m)
            ).pack(side='left', padx=6)

        # Legend
        legend = tk.Frame(parent, bg=BG_PANEL, height=22)
        legend.pack(fill='x', pady=(0, 2))
        legend_items = [
            (ACCENT_RED,    'Disaster'),
            (MAP_PATH_BASE, 'Route'),
            ('white',       'Ambulance'),
            (ACCENT_YELLOW, 'Incident'),
            (ACCENT_BLUE,   'Hospital'),
            (ACCENT_ORANGE, 'Roadblock'),
        ]
        for col, lbl in legend_items:
            f = tk.Frame(legend, bg=BG_PANEL)
            f.pack(side='left', padx=6, pady=2)
            tk.Label(f, bg=col, width=2, height=1).pack(side='left', padx=(0, 3))
            tk.Label(f, text=lbl, bg=BG_PANEL, fg=GREY,
                     font=('Consolas', 7)).pack(side='left')

        # Map canvas
        map_px = GRID_SIZE * CELL_PX
        self.map_canvas = tk.Canvas(
            parent, width=map_px, height=map_px,
            bg=MAP_BLOCK, highlightthickness=1,
            highlightbackground=DARK_GREY, cursor='crosshair',
        )
        self.map_canvas.pack()
        self.map_canvas.bind('<Button-1>', self._on_map_click)
        self.map_canvas.bind('<Motion>', self._on_map_hover)

    # ── RIGHT PANEL ───────────────────────────────────────────────────────

    def _build_right_panel(self, parent):
        # ── Lives saved ───────────────────────────────────────────────────
        lf = tk.Frame(parent, bg=BG_CARD)
        lf.pack(fill='x', padx=6, pady=(8, 3))
        tk.Label(lf, text='Lives Saved', bg=BG_CARD, fg=GREY,
                 font=('Consolas', 9)).pack(anchor='w', padx=6, pady=(4, 0))
        self._lives_lbl = tk.Label(lf, text='1,346,300,000', bg=BG_CARD,
                                   fg=WHITE, font=('Consolas', 18, 'bold'))
        self._lives_lbl.pack(anchor='center', pady=(0, 4))

        # ── Metrics grid ──────────────────────────────────────────────────
        mf = tk.Frame(parent, bg=BG_PANEL)
        mf.pack(fill='x', padx=6, pady=(0, 3))
        metrics = [
            ('Missions', '0',    'completed'),
            ('Avg RT',   '0s',   'avg_rt'),
            ('Effic.',   '100%', 'efficiency'),
            ('Active',   '0',    'active_inc'),
        ]
        self._metric_vars: dict = {}
        for i, (label, init, key) in enumerate(metrics):
            col_frame = tk.Frame(mf, bg=BG_CARD)
            col_frame.grid(row=0, column=i, padx=2, pady=2, sticky='ew')
            mf.columnconfigure(i, weight=1)
            tk.Label(col_frame, text=label, bg=BG_CARD, fg=GREY,
                     font=('Consolas', 7)).pack(pady=(3, 0))
            var = tk.StringVar(value=init)
            self._metric_vars[key] = var
            tk.Label(col_frame, textvariable=var, bg=BG_CARD, fg=WHITE,
                     font=('Consolas', 9, 'bold')).pack(pady=(0, 3))

        # ── Charts canvas ─────────────────────────────────────────────────
        self.chart_canvas = tk.Canvas(
            parent, bg=BG_PANEL, width=224, height=240,
            highlightthickness=0
        )
        self.chart_canvas.pack(fill='x', padx=4)
        self._build_charts()

        # ── Decision panel ────────────────────────────────────────────────
        self._section_hdr(parent, '  AI Decision  ▲')

        dec_outer = tk.Frame(parent, bg=BG_CARD)
        dec_outer.pack(fill='both', expand=True, padx=6, pady=(2, 4))

        self._decision_text = tk.Text(
            dec_outer, bg=BG_CARD, fg=ACCENT_GREEN,
            font=('Consolas', 7), relief='flat',
            wrap='word', state='disabled', height=10,
            highlightthickness=0, bd=0,
        )
        self._decision_text.pack(fill='both', expand=True, padx=4, pady=4)
        # Configure tags for coloured text
        self._decision_text.tag_configure('title',   foreground=WHITE,  font=('Consolas', 8, 'bold'))
        self._decision_text.tag_configure('label',   foreground=GREY,   font=('Consolas', 7))
        self._decision_text.tag_configure('value',   foreground=WHITE,  font=('Consolas', 7, 'bold'))
        self._decision_text.tag_configure('crit',    foreground=ACCENT_RED)
        self._decision_text.tag_configure('urgent',  foreground=ACCENT_YELLOW)
        self._decision_text.tag_configure('ok',      foreground=ACCENT_GREEN)
        self._decision_text.tag_configure('sep',     foreground=DARK_GREY)

    def _section_hdr(self, parent, text):
        f = tk.Frame(parent, bg=BG_SEP)
        f.pack(fill='x', pady=(4, 0))
        tk.Label(f, text=text, bg=BG_SEP, fg=WHITE,
                 font=('Consolas', 9, 'bold'), pady=3
                 ).pack(side='left', padx=6)

    def _build_charts(self):
        c = self.chart_canvas

        # Title labels
        c.create_text(8, 8,   text='Hospital Capacity (%)', fill=WHITE,
                      font=('Consolas', 8, 'bold'), anchor='w', tags='static')
        c.create_text(8, 128, text='Resource Allocation', fill=WHITE,
                      font=('Consolas', 8, 'bold'), anchor='w', tags='static')

        # Hospital capacity — 5 hospitals, multi-color
        hosp_colors = [ACCENT_BLUE, ACCENT_TEAL, ACCENT_PURPLE,
                       ACCENT_GREEN, ACCENT_ORANGE]
        self._hosp_chart = BarChart(
            c, 20, 20, 200, 95,
            labels=['H1', 'H2', 'H3', 'H4', 'H5'],
            colors=hosp_colors,
        )

        # Resource allocation — ambulance states
        res_colors = [GREY, ACCENT_YELLOW, ACCENT_GREEN, ACCENT_RED, ACCENT_BLUE]
        self._res_chart = BarChart(
            c, 20, 140, 200, 90,
            labels=['Idle', 'ToInc', 'ToHsp', 'Incs', 'Done'],
            colors=res_colors,
        )

        # Seed
        self._hosp_chart.update([75, 85, 60, 90, 70])
        self._res_chart.update([2, 1, 1, 7, 0])

    # ─────────────────────────────────────────────────────────────────────────
    # MAP DRAWING
    # ─────────────────────────────────────────────────────────────────────────

    def _draw_map(self):
        c   = self.map_canvas
        g   = self.sim.grid
        px  = CELL_PX

        c.delete('all')

        # ── Background cells ─────────────────────────────────────────────
        for r in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                cell = g[r][col]
                x0, y0 = col * px, r * px
                x1, y1 = x0 + px, y0 + px

                fill = {
                    BLOCK:         MAP_BLOCK,
                    ROAD:          MAP_ROAD,
                    DISASTER_ZONE: MAP_DISASTER,
                    HOSPITAL:      MAP_HOSPITAL_BG,
                    INCIDENT:      MAP_INCIDENT_BG,
                    USER_BLOCK:    MAP_USER_BLOCK,
                }.get(cell, MAP_ROAD)

                c.create_rectangle(x0, y0, x1, y1,
                                   fill=fill, outline=MAP_GRID_LINE, width=1,
                                   tags='cell')

        # ── Disaster zone red overlay (stipple tint) ──────────────────────
        for r in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                if g[r][col] == DISASTER_ZONE:
                    c.create_rectangle(
                        col*px, r*px, col*px+px, r*px+px,
                        fill=ACCENT_RED, stipple='gray12', outline='', tags='cell'
                    )

        # ── User roadblocks — orange hatching ────────────────────────────
        for r in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                if g[r][col] == USER_BLOCK:
                    x0, y0 = col*px, r*px
                    c.create_rectangle(x0, y0, x0+px, y0+px,
                                       fill=ACCENT_ORANGE, outline='',
                                       stipple='gray50', tags='cell')
                    # Diagonal cross
                    c.create_line(x0, y0, x0+px, y0+px,
                                  fill='#6b2800', width=1, tags='cell')
                    c.create_line(x0+px, y0, x0, y0+px,
                                  fill='#6b2800', width=1, tags='cell')

        # ── A* paths (one per ambulance, unique colour) ───────────────────
        for amb in self.sim.ambulances:
            if not amb.path or amb.path_index >= len(amb.path):
                continue
            color = PATH_COLORS[(amb.id - 1) % len(PATH_COLORS)]
            prev  = None
            for i in range(amb.path_index - 1, len(amb.path)):
                pr, pc = amb.path[i]
                cx = pc * px + px // 2
                cy = pr * px + px // 2
                # Draw dot on each future path cell
                c.create_oval(cx-3, cy-3, cx+3, cy+3,
                              fill=color, outline='', tags='path')
                if prev:
                    c.create_line(prev[0], prev[1], cx, cy,
                                  fill=color, width=2, tags='path',
                                  dash=(4, 3))
                prev = (cx, cy)

        # ── Hospitals ─────────────────────────────────────────────────────
        for h in self.sim.hospitals:
            r, col = h.pos
            cx = col * px + px // 2
            cy = r   * px + px // 2
            # Outer glow
            c.create_oval(cx-13, cy-13, cx+13, cy+13,
                          fill='', outline=ACCENT_BLUE, width=2, tags='entity')
            # Fill circle
            c.create_oval(cx-11, cy-11, cx+11, cy+11,
                          fill='#1565c0', outline='', tags='entity')
            # Cross
            c.create_line(cx-5, cy, cx+5, cy, fill='white', width=2, tags='entity')
            c.create_line(cx, cy-5, cx, cy+5, fill='white', width=2, tags='entity')
            # Load % badge above
            load_pct = int(h.load_fraction * 100)
            badge_col = (ACCENT_RED   if load_pct > 85 else
                         ACCENT_YELLOW if load_pct > 60 else ACCENT_GREEN)
            c.create_text(cx, cy - 17, text=f'{load_pct}%',
                          fill=badge_col, font=('Consolas', 7, 'bold'),
                          tags='entity')
            # Hospital id
            c.create_text(cx + 13, cy + 13, text=f'#{h.id}',
                          fill=GREY, font=('Consolas', 6), tags='entity')

        # ── Incidents ─────────────────────────────────────────────────────
        for inc in self.sim.incidents:
            if not inc.active:
                continue
            r, col = inc.pos
            cx = col * px + px // 2
            cy = r   * px + px // 2
            # Triangle scales with severity
            sz = 8 + inc.severity   # 9–19 px
            pts = [cx, cy - sz, cx - sz + 2, cy + sz - 4, cx + sz - 2, cy + sz - 4]
            tri_col = (ACCENT_RED    if inc.severity >= 8 else
                       ACCENT_YELLOW if inc.severity >= 5 else '#c8a800')
            c.create_polygon(pts, fill=tri_col, outline='#6b4c00',
                             width=1, tags='entity')
            # Exclamation
            c.create_text(cx, cy + 3, text='!', fill=BG_DARK,
                          font=('Arial', 7, 'bold'), tags='entity')
            # Severity badge
            c.create_text(cx + sz, cy - sz + 3, text=str(inc.severity),
                          fill=WHITE, font=('Consolas', 6), tags='entity')

        # ── Ambulances (smoothly interpolated) ───────────────────────────
        for amb in self.sim.ambulances:
            # Compute interpolated draw position
            prog = self._smooth_progress.get(amb.id, 1.0)
            pr, pc   = amb.pos
            pr2, pc2 = amb.prev_pos

            draw_r = pr2 + (pr - pr2) * prog
            draw_c = pc2 + (pc - pc2) * prog

            cx = int(draw_c * px + px / 2)
            cy = int(draw_r * px + px / 2)

            # Highlight ring for selected ambulance
            if amb.highlighted or amb.state != 'idle':
                ring_col = PATH_COLORS[(amb.id - 1) % len(PATH_COLORS)]
                c.create_oval(cx-13, cy-13, cx+13, cy+13,
                              fill='', outline=ring_col, width=2,
                              dash=(3, 2), tags='entity')

            # Van body
            c.create_rectangle(cx - AMB_W, cy - AMB_H,
                               cx + AMB_W, cy + AMB_H,
                               fill='#dde8f0', outline=GREY, width=1,
                               tags='entity')
            # Cab section
            c.create_rectangle(cx - AMB_W, cy - AMB_H,
                               cx - 2, cy + AMB_H,
                               fill='#c0d0e0', outline='', tags='entity')
            # Red cross
            c.create_line(cx + 3, cy - 3, cx + 3, cy + 3,
                          fill=ACCENT_RED, width=2, tags='entity')
            c.create_line(cx, cy, cx + 6, cy,
                          fill=ACCENT_RED, width=2, tags='entity')
            # Unit id
            c.create_text(cx, cy + AMB_H + 7, text=f'U{amb.id}',
                          fill=WHITE, font=('Consolas', 6), tags='entity')

    # ─────────────────────────────────────────────────────────────────────────
    # SMOOTH ANIMATION LOOP  (runs at ~30 fps independent of sim speed)
    # ─────────────────────────────────────────────────────────────────────────

    def _start_smooth_loop(self):
        self._smooth_running = True
        self._smooth_step()

    def _smooth_step(self):
        if not self._smooth_running:
            return
        # Advance progress for each moving ambulance
        step = 0.15 * self.sim.speed
        changed = False
        for amb in self.sim.ambulances:
            cur = self._smooth_progress.get(amb.id, 1.0)
            if cur < 1.0:
                new = min(1.0, cur + step)
                self._smooth_progress[amb.id] = new
                changed = True
            else:
                self._smooth_progress[amb.id] = 1.0

        if changed:
            # Redraw only entity layer for performance
            self._redraw_entities()

        self.root.after(33, self._smooth_step)   # ~30 fps

    def _redraw_entities(self):
        """Fast partial redraw — only entity + path layers."""
        c = self.map_canvas
        c.delete('entity')
        c.delete('path')
        px = CELL_PX

        # Paths
        for amb in self.sim.ambulances:
            if not amb.path or amb.path_index >= len(amb.path):
                continue
            color = PATH_COLORS[(amb.id - 1) % len(PATH_COLORS)]
            prev  = None
            for i in range(max(0, amb.path_index - 1), len(amb.path)):
                pr, pc_ = amb.path[i]
                cx = pc_ * px + px // 2
                cy = pr  * px + px // 2
                c.create_oval(cx-2, cy-2, cx+2, cy+2,
                              fill=color, outline='', tags='path')
                if prev:
                    c.create_line(prev[0], prev[1], cx, cy,
                                  fill=color, width=2, tags='path',
                                  dash=(4, 3))
                prev = (cx, cy)

        # Hospitals
        for h in self.sim.hospitals:
            r, col = h.pos
            cx = col*px + px//2; cy = r*px + px//2
            c.create_oval(cx-13, cy-13, cx+13, cy+13,
                          fill='', outline=ACCENT_BLUE, width=2, tags='entity')
            c.create_oval(cx-11, cy-11, cx+11, cy+11,
                          fill='#1565c0', outline='', tags='entity')
            c.create_line(cx-5, cy, cx+5, cy, fill='white', width=2, tags='entity')
            c.create_line(cx, cy-5, cx, cy+5, fill='white', width=2, tags='entity')
            load_pct = int(h.load_fraction * 100)
            badge_col = (ACCENT_RED if load_pct > 85 else
                         ACCENT_YELLOW if load_pct > 60 else ACCENT_GREEN)
            c.create_text(cx, cy-17, text=f'{load_pct}%',
                          fill=badge_col, font=('Consolas', 7, 'bold'), tags='entity')
            c.create_text(cx+13, cy+13, text=f'#{h.id}',
                          fill=GREY, font=('Consolas', 6), tags='entity')

        # Incidents
        for inc in self.sim.incidents:
            if not inc.active: continue
            r, col = inc.pos
            cx = col*px + px//2; cy = r*px + px//2
            sz = 8 + inc.severity
            pts = [cx, cy-sz, cx-sz+2, cy+sz-4, cx+sz-2, cy+sz-4]
            tri_col = (ACCENT_RED if inc.severity >= 8 else
                       ACCENT_YELLOW if inc.severity >= 5 else '#c8a800')
            c.create_polygon(pts, fill=tri_col, outline='#6b4c00',
                             width=1, tags='entity')
            c.create_text(cx, cy+3, text='!', fill=BG_DARK,
                          font=('Arial', 7, 'bold'), tags='entity')
            c.create_text(cx+sz, cy-sz+3, text=str(inc.severity),
                          fill=WHITE, font=('Consolas', 6), tags='entity')

        # Ambulances
        for amb in self.sim.ambulances:
            prog = self._smooth_progress.get(amb.id, 1.0)
            pr, pc   = amb.pos
            pr2, pc2 = amb.prev_pos
            draw_r   = pr2 + (pr - pr2) * prog
            draw_c   = pc2 + (pc - pc2) * prog
            cx = int(draw_c * px + px / 2)
            cy = int(draw_r * px + px / 2)

            if amb.highlighted or amb.state != 'idle':
                ring_col = PATH_COLORS[(amb.id - 1) % len(PATH_COLORS)]
                c.create_oval(cx-13, cy-13, cx+13, cy+13,
                              fill='', outline=ring_col, width=2,
                              dash=(3, 2), tags='entity')
            c.create_rectangle(cx-AMB_W, cy-AMB_H, cx+AMB_W, cy+AMB_H,
                               fill='#dde8f0', outline=GREY, width=1, tags='entity')
            c.create_rectangle(cx-AMB_W, cy-AMB_H, cx-2, cy+AMB_H,
                               fill='#c0d0e0', outline='', tags='entity')
            c.create_line(cx+3, cy-3, cx+3, cy+3,
                          fill=ACCENT_RED, width=2, tags='entity')
            c.create_line(cx, cy, cx+6, cy,
                          fill=ACCENT_RED, width=2, tags='entity')
            c.create_text(cx, cy+AMB_H+7, text=f'U{amb.id}',
                          fill=WHITE, font=('Consolas', 6), tags='entity')

    # ─────────────────────────────────────────────────────────────────────────
    # LEFT PANEL REFRESH
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_units(self):
        for w in self._units_frame.winfo_children():
            w.destroy()

        state_label = {
            'idle':              ('● IDLE',       GREY),
            'en_route_incident': ('→ TO INCIDENT', ACCENT_YELLOW),
            'en_route_hospital': ('→ TO HOSPITAL', ACCENT_GREEN),
        }

        for amb in self.sim.ambulances:
            slabel, scolor = state_label.get(amb.state, ('● IDLE', GREY))

            f = tk.Frame(self._units_frame, bg=BG_CARD)
            f.pack(fill='x', padx=4, pady=1)

            # State colour strip
            tk.Label(f, bg=scolor, width=2).pack(side='left')

            inner = tk.Frame(f, bg=BG_CARD)
            inner.pack(side='left', fill='x', expand=True, padx=4, pady=2)

            row1 = tk.Frame(inner, bg=BG_CARD)
            row1.pack(fill='x')
            tk.Label(row1, text=f'Unit {amb.id}', bg=BG_CARD, fg=WHITE,
                     font=('Consolas', 8, 'bold')).pack(side='left')
            tk.Label(row1, text=slabel, bg=BG_CARD, fg=scolor,
                     font=('Consolas', 7)).pack(side='right')

            # Show assignment info
            if amb.target_incident:
                tk.Label(inner, text=f'→ Inc #{amb.target_incident}  Hosp #{amb.target_hospital}',
                         bg=BG_CARD, fg=GREY, font=('Consolas', 7)).pack(anchor='w')
            else:
                tk.Label(inner, text='Awaiting dispatch',
                         bg=BG_CARD, fg=DARK_GREY, font=('Consolas', 7)).pack(anchor='w')

            tk.Label(f, text=amb.display_time, bg=BG_CARD, fg=GREY,
                     font=('Consolas', 7)).pack(side='right', padx=4)

    def _refresh_incidents(self):
        for w in self._incidents_frame.winfo_children():
            w.destroy()

        active = sorted(self.sim.active_incidents(), key=lambda x: -x.severity)[-7:]
        for inc in active:
            sev_col = (ACCENT_RED    if inc.severity >= 8 else
                       ACCENT_YELLOW if inc.severity >= 5 else GREY)
            f = tk.Frame(self._incidents_frame, bg=BG_CARD)
            f.pack(fill='x', padx=4, pady=1)

            tk.Label(f, bg=sev_col, width=2).pack(side='left')
            inner = tk.Frame(f, bg=BG_CARD)
            inner.pack(side='left', fill='x', expand=True, padx=4, pady=2)

            row1 = tk.Frame(inner, bg=BG_CARD)
            row1.pack(fill='x')
            tk.Label(row1, text=f'Incident #{inc.id}', bg=BG_CARD, fg=sev_col,
                     font=('Consolas', 8, 'bold')).pack(side='left')
            # Severity bar (small dots)
            sbar = '▮' * inc.severity + '▯' * (10 - inc.severity)
            tk.Label(row1, text=f'{sbar}', bg=BG_CARD, fg=sev_col,
                     font=('Consolas', 5)).pack(side='right')

            status = '🚑 Assigned' if inc.assigned else '⏳ Waiting'
            tk.Label(inner, text=f'Sev {inc.severity}/10  {status}',
                     bg=BG_CARD, fg=GREY, font=('Consolas', 7)).pack(anchor='w')

            tk.Label(f, text=inc.display_time, bg=BG_CARD, fg=GREY,
                     font=('Consolas', 7)).pack(side='right', padx=4)

    # ─────────────────────────────────────────────────────────────────────────
    # RIGHT PANEL REFRESH
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_right(self):
        # Lives saved
        self._lives_lbl.config(text=f'{self.sim.lives_saved:,}')

        # Metric cards
        self._metric_vars['completed'].set(str(self.sim.completed_missions))
        avg_rt = self.sim.avg_response_time()
        self._metric_vars['avg_rt'].set(f'{avg_rt:.0f}s')
        self._metric_vars['efficiency'].set(f'{self.sim.efficiency_pct:.0f}%')
        self._metric_vars['active_inc'].set(str(len(self.sim.active_incidents())))

        # Hospital capacity bars
        loads = [int(h.load_fraction * 100) for h in self.sim.hospitals]
        while len(loads) < 5: loads.append(0)
        self._hosp_chart.update(loads[:5])

        # Resource allocation bars
        idle    = sum(1 for a in self.sim.ambulances if a.state == 'idle')
        to_inc  = sum(1 for a in self.sim.ambulances if a.state == 'en_route_incident')
        to_hosp = sum(1 for a in self.sim.ambulances if a.state == 'en_route_hospital')
        n_inc   = len(self.sim.active_incidents())
        done    = self.sim.completed_missions
        self._res_chart.update([idle, to_inc, to_hosp, n_inc, min(20, done)])

        # Decision panel
        self._refresh_decision_panel()

    def _refresh_decision_panel(self):
        dr = self.sim.latest_decision
        t  = self._decision_text
        t.config(state='normal')
        t.delete('1.0', 'end')

        if dr is None:
            t.insert('end', '  No dispatch yet.\n  Press START to begin.\n', 'label')
        else:
            sep = '━' * 24 + '\n'
            t.insert('end', sep, 'sep')

            t.insert('end', '  AMBULANCE  : ', 'label')
            t.insert('end', f'Unit {dr.ambulance_id}\n', 'value')

            # Severity with colour
            sev_tag = 'crit' if dr.severity >= 8 else ('urgent' if dr.severity >= 5 else 'ok')
            t.insert('end', '  INCIDENT   : ', 'label')
            t.insert('end', f'#{dr.incident_id}  ', 'value')
            t.insert('end', f'sev {dr.severity}/10\n', sev_tag)

            # Hospital load with colour
            load_tag = 'crit' if dr.hospital_load_pct > 85 else (
                'urgent' if dr.hospital_load_pct > 60 else 'ok')
            t.insert('end', '  HOSPITAL   : ', 'label')
            t.insert('end', f'#{dr.hospital_id}  ', 'value')
            t.insert('end', f'{dr.hospital_load_pct}% load\n', load_tag)

            t.insert('end', '  DISTANCE   : ', 'label')
            t.insert('end', f'{dr.distance_cells} cells\n', 'value')

            t.insert('end', '  PATH LEN   : ', 'label')
            t.insert('end', f'{dr.path_length} steps\n', 'value')

            t.insert('end', '  SCORE      : ', 'label')
            t.insert('end', f'{dr.heuristic_score:.2f}\n', 'value')

            t.insert('end', '  FORMULA    : ', 'label')
            t.insert('end', f'{dr.score_breakdown}\n', 'ok')

            t.insert('end', sep, 'sep')
            t.insert('end', f'  {dr.reason}\n', sev_tag)

        t.config(state='disabled')

    # ─────────────────────────────────────────────────────────────────────────
    # CALLBACKS
    # ─────────────────────────────────────────────────────────────────────────

    def _on_map_click(self, event):
        col = event.x // CELL_PX
        row = event.y // CELL_PX
        if not (0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE):
            return

        mode = self._click_mode_var.get()

        if mode == 'block':
            self.sim.toggle_block(row, col)
            self._draw_map()

        elif mode == 'incident':
            self.sim.add_incident(row, col)
            self._draw_map()

        elif mode == 'severity':
            # Find incident in a small radius
            for dr in range(-1, 2):
                for dc in range(-1, 2):
                    inc = self.sim.incident_at(row + dr, col + dc)
                    if inc:
                        self.sim.increase_severity(inc.id)
                        self._draw_map()
                        self._refresh_units()
                        self._refresh_incidents()
                        self._refresh_right()
                        return

    def _on_map_hover(self, event):
        """Show tooltip with cell info."""
        col = event.x // CELL_PX
        row = event.y // CELL_PX
        # Could add a tooltip label — skipping to keep widget count low

    def _on_start(self):
        if not self.sim.running:
            self.sim.running = True
            self._btn_start.config(text='● RUNNING', bg='#1f5c2e')
            self._btn_pause.config(text='⏸ PAUSE')
            self._sim_tick()

    def _on_pause(self):
        self.sim.running = not self.sim.running
        if self.sim.running:
            self._btn_pause.config(text='⏸ PAUSE')
            self._btn_start.config(text='● RUNNING', bg='#1f5c2e')
            self._sim_tick()
        else:
            self._btn_pause.config(text='▶ RESUME')
            self._btn_start.config(text='▶ START', bg=ACCENT_GREEN)

    def _on_reset(self):
        self.sim.running = False
        self._btn_start.config(text='▶ START', bg=ACCENT_GREEN)
        self._btn_pause.config(text='⏸ PAUSE')
        self.sim.reset()
        self._smooth_progress.clear()
        self._draw_map()
        self._refresh_units()
        self._refresh_incidents()
        self._refresh_right()
        self.sim.dispatch_all()

    def _on_demo(self):
        """Demo mode: auto-start + print decision details for each dispatch."""
        self.sim.demo_mode = True
        if not self.sim.running:
            self._on_start()
        # Force a fresh dispatch to populate the decision panel
        self.sim.dispatch_all()
        self._refresh_right()

    def _set_speed(self, v: float):
        self.sim.speed = v
        self._speed_var.set(v)

    def _toggle_debug(self):
        algorithms.DEBUG_MODE = self._debug_var.get()

    # ─────────────────────────────────────────────────────────────────────────
    # SIMULATION TICK
    # ─────────────────────────────────────────────────────────────────────────

    def _sim_tick(self):
        if not self.sim.running:
            return
        self.sim.step()
        # Start smooth animation for any ambulance that just moved
        for amb in self.sim.ambulances:
            if amb.path_progress < 0.5:   # just moved
                self._smooth_progress[amb.id] = 0.0
        delay = max(80, int(600 / self.sim.speed))
        self.root.after(delay, self._sim_tick)

    def _on_sim_tick(self):
        """Called by simulation after every step."""
        self._refresh_units()
        self._refresh_incidents()
        self._refresh_right()

    def _update_clock(self):
        t = time.strftime('%H:%M:%S  %Y-%m-%d')
        self._lbl_time.config(text=t)
        self.root.after(1000, self._update_clock)

    # ─────────────────────────────────────────────────────────────────────────
    # ENTRY POINT
    # ─────────────────────────────────────────────────────────────────────────

    def run(self):
        self._refresh_units()
        self._refresh_incidents()
        self._refresh_right()
        self.root.mainloop()
