"""
main.py  ·  v2
==============
Entry point for the AI Disaster Response Planner.

Usage
-----
    python main.py               # normal mode
    python main.py --debug       # enable AI debug logging to console
    python main.py --demo        # start in demo mode (auto-runs + narrates)
    python main.py --debug --demo
"""

import sys
import algorithms   # imported before ui so flag can be set pre-launch


def main():
    debug = '--debug' in sys.argv
    demo  = '--demo'  in sys.argv

    if debug:
        algorithms.DEBUG_MODE = True
        print("[AI DEBUG] Debug mode enabled — AI decisions will be printed.")

    from simulation import Simulation
    from ui import DashboardApp

    sim = Simulation()
    app = DashboardApp(sim)

    if demo:
        # Flip the checkbox on and trigger demo immediately after mainloop starts
        app.root.after(500, app._on_demo)

    app.run()


if __name__ == '__main__':
    main()
