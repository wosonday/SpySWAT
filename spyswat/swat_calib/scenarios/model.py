"""Plain, picklable data classes describing a scenario batch."""
import numbers
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CIO_KEYS = ("NBYR", "IYR", "IDAF", "IDAL", "IPRINT", "NYSKIP")


def validate_name(kind: str, name) -> str:
    """Names end up in file names: letters, digits, '.', '_' and '-' only."""
    if not isinstance(name, str) or not name:
        raise ValueError(f"{kind} name must be a non-empty string, got {name!r}")
    if "__" in name:
        raise ValueError(
            f"{kind} name {name!r} must not contain '__' (two underscores): it separates "
            f"scenario and parameter set in the job id, so different pairs could collide")
    if not _NAME_RE.match(name) or name.endswith("."):
        raise ValueError(
            f"{kind} name {name!r} is not safe as a file name: use letters, digits, "
            f"'.', '_' or '-' (starting with a letter or digit)")
    return name


@dataclass
class Scenario:
    """One simulation context.

    Args:
        name:        unique label (also used in result file names).
        txinout_dir: a complete, separate TxtInOut folder for this scenario
                     (e.g. one folder per land-use map). None = the project's own
                     base TxtInOut.
        weather_dir: folder whose files are copied BY FILE NAME over the worker's
                     files before the run (pcp1.pcp, tmp1.tmp, ...). The files must
                     already be in SWAT TxtInOut format; converting station .txt
                     files (e.g. GCM output) into that format is out of scope.
                     The overlay is undone for the next job that uses the same
                     worker folder.
        cio:         optional dict applied with ``FileCIO.set(**cio)``; allowed keys
                     NBYR, IYR, IDAF, IDAL, IPRINT, NYSKIP (integers), e.g. a
                     different simulation period for a GCM period.
        evaluate:    True (historical scenario): metrics are computed against the
                     observations. False (future / GCM projection): never evaluated; no
                     observation-step check, no metric rows, observations are not sent
                     to its jobs; its series are written as usual. An evaluated scenario
                     whose period shares no dates with the observations is treated like
                     evaluate=False for that job (note in summary.csv).
    """
    name: str
    txinout_dir: Optional[Union[str, Path]] = None
    weather_dir: Optional[Union[str, Path]] = None
    cio: Optional[Dict[str, int]] = None
    evaluate: bool = True

    def __post_init__(self):
        validate_name("Scenario", self.name)
        if not isinstance(self.evaluate, bool):
            raise ValueError(f"Scenario {self.name!r}: evaluate must be True or False")
        for attr in ("txinout_dir", "weather_dir"):
            val = getattr(self, attr)
            if val is None:
                continue
            p = Path(val)
            if not p.is_dir():
                raise FileNotFoundError(f"Scenario {self.name!r}: {attr} is not an existing "
                                        f"directory: {str(p)!r}")
            setattr(self, attr, str(p))
        if self.cio is not None:
            if not isinstance(self.cio, dict):
                raise ValueError(f"Scenario {self.name!r}: cio must be a dict")
            unknown = sorted(set(self.cio) - set(_CIO_KEYS))
            if unknown:
                raise ValueError(f"Scenario {self.name!r}: unknown cio key(s) {unknown}; "
                                 f"allowed: {list(_CIO_KEYS)}")
            for k, v in self.cio.items():
                if isinstance(v, bool) or not isinstance(v, numbers.Integral):
                    raise ValueError(f"Scenario {self.name!r}: cio[{k!r}] must be an integer, "
                                     f"got {v!r}")
            self.cio = {k: int(v) for k, v in self.cio.items()} or None


def _norm_group(key: str, group) -> tuple:
    if not isinstance(group, (tuple, list)) or len(group) < 2:
        raise ValueError(f"Parameter {key!r}: expected (value, method[, subbasins]), "
                         f"got {group!r}")
    value, method = group[0], group[1]
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        value = float(value)
    out = (value, str(method))
    if len(group) > 2 and group[2] is not None and group[2] != "All":
        subs = group[2]
        if isinstance(subs, str):
            subs = [int(float(s)) for s in subs.split(",")]
        elif isinstance(subs, numbers.Integral):
            subs = [int(subs)]
        else:
            subs = [int(s) for s in subs]
        out = out + (subs,)
    return out


@dataclass
class ParamSet:
    """A named set of parameter edits, in the format of ``HRUManager.update_params``:
    ``{'CN2.mgt': [(value, method[, subbasins]), ...]}`` (passes applied in order).
    An empty ParamSet runs the scenario unchanged."""
    name: str
    updates: Dict[str, List[tuple]] = field(default_factory=dict)

    def __post_init__(self):
        validate_name("ParamSet", self.name)
        if not isinstance(self.updates, dict):
            raise ValueError(f"ParamSet {self.name!r}: updates must be a dict")
        norm: Dict[str, List[tuple]] = {}
        for key, groups in self.updates.items():
            if not isinstance(key, str) or "." not in key:
                raise ValueError(f"ParamSet {self.name!r}: parameter {key!r} must use the "
                                 f"'name.ext' format, e.g. 'CN2.mgt'")
            if isinstance(groups, tuple):
                groups = [groups]
            norm[key] = [_norm_group(key, g) for g in groups]
        self.updates = norm

    @classmethod
    def from_dict(cls, name: str, params: Dict[str, Any]) -> "ParamSet":
        """``{key: value}`` means method 'v'; a tuple or list of tuples is used as is."""
        updates: Dict[str, Any] = {}
        for key, val in params.items():
            if isinstance(val, (tuple, list)):
                updates[key] = val
            else:
                updates[key] = [(val, "v")]
        return cls(name, updates)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, name: str, param: str = "param",
                       method: str = "method", value: str = "value",
                       sub: str = "subbasin") -> "ParamSet":
        """Same row semantics as ``HRUManager.update_by_df``: one pass per row, in row
        order (the same parameter may appear several times); a missing parameter name
        skips the row; subbasin None/NaN/'All' = all subbasins, otherwise '71,45,70'."""
        updates: Dict[str, List[tuple]] = {}
        has_sub = sub in df.columns
        for _, row in df.iterrows():
            p_raw = row[param]
            if pd.isna(p_raw):
                continue
            pname = str(p_raw)
            if "." not in pname:
                raise ValueError(f"Param '{pname}' in DataFrame missing file extension. "
                                 f"Use 'name.ext' format, e.g. 'CN2.mgt'.")
            raw_sub = row[sub] if has_sub else None
            if raw_sub is None or pd.isna(raw_sub) or raw_sub == "All":
                group = (row[value], row[method])
            else:
                subs = [int(float(s)) for s in str(raw_sub).split(",")]
                group = (row[value], row[method], subs)
            updates.setdefault(pname, []).append(group)
        return cls(name, updates)


@dataclass
class Job:
    scenario: Scenario
    param_set: ParamSet

    @property
    def job_id(self) -> str:
        return f"{self.scenario.name}__{self.param_set.name}"


@dataclass
class RunResult:
    job_id: str
    scenario: str
    param_set: str
    status: str                      # 'ok' | 'failed' | 'skipped'
    error: Optional[str] = None
    duration_s: float = 0.0
    n_rows: int = 0
    series_path: Optional[str] = None
    evaluated: bool = True           # False: no metrics for this job (see eval_note)
    eval_note: Optional[str] = None
