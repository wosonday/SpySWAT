"""Pure helpers for calibration parameter specifications and log columns."""

from typing import Dict, Tuple


def parse_spec(param_ranges: dict) -> Tuple[dict, dict, dict]:
    """
    Parse unified param_ranges into (bounds, methods, subbasins).

    Supported formats (can mix freely in same dict):
        "CN2.mgt": (60, 98)                        # old format -- bounds only
        "CN2.mgt": ((60, 98), "r")                 # bounds + method
        "CN2.mgt": ((60, 98), "r", [71, 45, 70])  # bounds + method + subbasins
    """
    bounds, methods, subbasins = {}, {}, {}
    for name, spec in param_ranges.items():
        if isinstance(spec[0], (int, float)):
            # Old format: (min, max)
            if len(spec) > 2:
                raise ValueError(
                    f"Parameter '{name}': old format (min, max) accepts exactly 2 values, "
                    f"got {len(spec)}. Use new format: ((min, max), method, subbasins)."
                )
            bounds[name] = (float(spec[0]), float(spec[1]))
        else:
            # New format: ((min, max), method?, subbasins?)
            bounds[name] = (float(spec[0][0]), float(spec[0][1]))
            if len(spec) >= 2 and spec[1] is not None:
                methods[name] = spec[1]
            if len(spec) >= 3 and spec[2] is not None:
                subbasins[name] = spec[2]
    return bounds, methods, subbasins


def format_params(raw: dict, methods: dict = None, subbasins: dict = None) -> dict:
    """Convert {name: float} -> {name: [(val, method, [subs])]}."""
    _m = methods   or {}
    _s = subbasins or {}
    out = {}
    for name, val in raw.items():
        method = _m.get(name, "v")
        subs   = _s.get(name)
        out[name] = [(float(val), method, subs)] if subs is not None else [(float(val), method)]
    return out


def is_raw(param_dict: dict) -> bool:
    """True if {name: float}, False if already formatted {name: [tuple]}."""
    for v in param_dict.values():
        return isinstance(v, (int, float))
    return True


def param_columns(params: dict) -> Dict[str, tuple]:
    """{name: (first value, first method, full spec text)} of every formatted parameter."""
    out = {}
    for name, groups in (params or {}).items():
        if isinstance(groups, tuple):
            groups = [groups]
        parts = []
        for g in groups:
            subs = g[2] if len(g) > 2 else None
            subs_txt = ("All" if subs is None or subs == "All" else
                        ",".join(str(x) for x in (subs if isinstance(subs, (list, tuple, set))
                                                  else [subs])))
            parts.append(f"{format(float(g[0]), '.10g')}:{g[1] if len(g) > 1 else 'v'}:{subs_txt}")
        first = groups[0]
        out[name] = (first[0], first[1] if len(first) > 1 else "v", "|".join(parts))
    return out
