"""
FigViewer — thin wrapper around _build_fig_viewer.py.

Usage via SWATProject:
    path = project.fig_viewer(red_reaches=[32, 33])

Standalone:
    from spyswat.swat_calib.visualization import FigViewer
    viewer = FigViewer("path/to/TxtInOut")
    path = viewer.build(red_reaches=[32, 33])
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Optional, Union

from ._build_fig_viewer import parse_fig, html_page


class FigViewer:
    """Parse SWAT fig.fig and build an interactive HTML viewer."""

    def __init__(self, txinout_dir: Union[str, Path]):
        self._fig_path = Path(txinout_dir) / "fig.fig"
        if not self._fig_path.exists():
            raise FileNotFoundError(f"fig.fig not found in {txinout_dir}")

    def parse(self, red_reaches: Optional[list] = None) -> dict:
        return parse_fig(self._fig_path, set(red_reaches or []))

    def build(
        self,
        red_reaches: Optional[list] = None,
        output_path: Optional[Union[str, Path]] = None,
        open_browser: bool = True,
    ) -> Path:
        data = parse_fig(self._fig_path, set(red_reaches or []))
        out  = Path(output_path) if output_path else self._fig_path.parent / "fig_viewer.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_page(data), encoding="utf-8", newline="\n")

        print(f"[FigViewer] Saved → {out}")
        print(f"[FigViewer] Commands: {len(data['commands'])} | Issues: {len(data['issues'])}"
              + (f" | Redpoints: {sorted(set(red_reaches or []))}" if red_reaches else ""))

        if open_browser:
            webbrowser.open(out.as_uri())
        return out
