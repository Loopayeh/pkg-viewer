#!/usr/bin/env python3
"""Reproduce issue: mkbtn ttk fallback crashes on RoundedButton-only kwargs.

Simulates a machine without PIL (Debian 13 .deb install) by blocking the
PIL import, then calls mkbtn exactly like run_gui does for the "Copy"
cidrow button (kind="mini") inside an Xvfb display.
"""
import os
import sys

# Block PIL so mkbtn takes the ttk.Button fallback path (no RoundedButton).
sys.modules["PIL"] = None

# Import the full app module (defines styles, fonts, constants).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pkgviewer  # noqa: E402

import tkinter as tk  # noqa: E402

root = tk.Tk()
root.withdraw()

# Same call as the crash site (pkgviewer.py run_gui -> cidrow "Copy"):
try:
    btn = pkgviewer.mkbtn(root, text="Copy", style="Ghost.TButton",
                          bg=pkgviewer.CARD,
                          kind="mini", font=(pkgviewer.FONT[0], 9),
                          command=lambda: None)
    btn.pack(side="left", padx=(6, 8))
    print("OK: mkbtn(kind=...) fallback survived ->", type(btn).__name__)
    rc = 0
except tk.TclError as ex:
    print("CRASH:", ex)
    rc = 1
finally:
    root.destroy()
sys.exit(rc)
