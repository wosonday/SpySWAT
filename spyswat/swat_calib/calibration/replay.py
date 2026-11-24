"""Resume by replay: an ordered cursor over the committed runs of a session.

API-5.  ``ReplayCursor`` answers the parameter sets an algorithm proposes on a
resumed run from the runs already committed in a ``SessionStore``, so SWAT is
never re-run for a stored result.  The cursor is *ordered*: run k of the new
execution must equal stored row k exactly (same parameter key order, canonical
floats), otherwise ``ResumeMismatchError`` names the offending run.

Nothing here imports from ``calib_manager`` or ``session_store``: the cursor is
duck-typed against the store's ``runs()`` / ``site_metrics()`` / ``param_names``
/ ``sites`` surface, so it cannot create an import cycle.
"""

from __future__ import annotations


def _canon_float(value) -> float:
    """Canonical float for exact comparison: ``-0.0`` normalised to ``0.0``."""
    f = float(value)
    return 0.0 if f == 0 else f


def _raw_params(params: dict) -> dict:
    """Return raw ``{name: float}`` from a raw or pre-formatted param dict.

    A formatted value is ``[(value, method[, subbasins]), ...]`` (or a bare
    ``(value, method[, subbasins])`` tuple); the first group's value is taken.
    Raw ``{name: float}`` dicts pass through unchanged.
    """
    out = {}
    for name, spec in (params or {}).items():
        if isinstance(spec, (list, tuple)):
            first = spec[0] if spec else None
            out[name] = first[0] if isinstance(first, (list, tuple)) else first
        else:
            out[name] = spec
    return out


class ResumeMismatchError(ValueError):
    """A resumed run's parameter sequence no longer matches the stored one."""


class StoredRun:
    """One committed run as recorded in ``runs.csv`` (plus per-site metrics)."""

    __slots__ = ("run_id", "params", "status", "error", "score",
                 "is_initial", "site_metrics")

    def __init__(self, run_id, params, status, error, score, is_initial,
                 site_metrics):
        self.run_id = run_id
        self.params = params            # {name: float}
        self.status = status            # "ok" | "failed"
        self.error = error              # "" for ok
        self.score = score              # float (NaN for a failed run)
        self.is_initial = is_initial    # bool
        self.site_metrics = site_metrics  # {(var, reach): {"<m>_calib": ...}}

    def __repr__(self):
        return (
            f"StoredRun(run_id={self.run_id!r}, status={self.status!r}, "
            f"score={self.score!r})"
        )


class ReplayCursor:
    """Ordered cursor over the committed runs of an opened ``SessionStore``.

    Stored run ids must be exactly ``1..k`` (no gaps, duplicates or non-1
    start); an empty session is valid.  ``take()`` consumes the cursor in
    submission order: entry k of the new execution is compared to stored row k
    (canonical floats, exact equality) and answered with the matching
    ``StoredRun``; once the cursor is exhausted every further entry is ``None``.
    """

    def __init__(self, store):
        self._store = store
        self._param_names = list(store.param_names)
        self._sites = [tuple(site) for site in store.sites]
        runs_df = store.runs()
        self._runs = self._build_runs(runs_df, store)
        self._pos = 0

    # ------------------------------------------------------------------ build

    def _build_runs(self, runs_df, store):
        if runs_df is None or len(runs_df) == 0:
            return []

        # Read every site's committed metrics once, keyed by run id, so a run
        # whose metric file is missing (e.g. every run failed) yields an empty
        # mapping instead of an error.
        site_metrics_by_run = {}
        for (var, reach) in self._sites:
            frame = store.site_metrics(var, reach)
            if frame is None or len(frame) == 0:
                continue
            metric_cols = [c for c in frame.columns if c != "run_id"]
            for _, row in frame.iterrows():
                rid = int(row["run_id"])
                site_metrics_by_run.setdefault(rid, {})[(var, reach)] = {
                    c: float(row[c]) for c in metric_cols
                }

        runs = []
        ids = []
        for _, row in runs_df.iterrows():
            run_id = int(row["run_id"])
            ids.append(run_id)
            runs.append(StoredRun(
                run_id=run_id,
                params={name: float(row[name]) for name in self._param_names},
                status=str(row["status"]),
                error="" if row["error"] is None else str(row["error"]),
                score=float(row["score"]),
                is_initial=bool(row["is_initial"]),
                site_metrics=site_metrics_by_run.get(run_id, {}),
            ))

        if ids != list(range(1, len(ids) + 1)):
            raise ResumeMismatchError(
                f"stored run ids must be exactly 1..{len(ids)} (no gaps, "
                f"duplicates or non-1 start); got {ids!r}"
            )
        return runs

    # --------------------------------------------------------------- read-only

    @property
    def remaining(self) -> int:
        """Number of committed runs still ahead of the cursor."""
        return len(self._runs) - self._pos

    @property
    def next_run_id(self) -> int:
        """The run id a live run should get next (``1`` for an empty session)."""
        if not self._runs:
            return 1
        return self._runs[-1].run_id + 1

    # ------------------------------------------------------------------ consume

    def take(self, param_sets):
        """Answer ``param_sets`` from the store, in submission order.

        Returns a list the same length as ``param_sets``: a ``StoredRun`` for
        each entry that matched a committed run, ``None`` for every entry past
        the cursor (those must be run).  A mismatch raises
        ``ResumeMismatchError`` without advancing the cursor.
        """
        out = []
        pos = self._pos
        for params in param_sets:
            if pos >= len(self._runs):
                out.append(None)
                continue
            stored = self._runs[pos]
            self._check(stored, params)
            pos += 1
            out.append(stored)
        # Only advance the cursor once EVERY entry passed ``_check``, so a
        # mismatch mid-batch leaves the cursor exactly where it was.
        self._pos = pos
        return out

    def _check(self, stored, params) -> None:
        given = _raw_params(params)
        given_names = list(given)
        if given_names != self._param_names:
            raise ResumeMismatchError(
                f"resume mismatch at run {stored.run_id}: parameter key order "
                f"{given_names!r} does not match the stored order "
                f"{self._param_names!r}"
            )
        for name in self._param_names:
            stored_val = _canon_float(stored.params[name])
            new_val = _canon_float(given[name])
            if stored_val != new_val:
                raise ResumeMismatchError(
                    f"resume mismatch at run {stored.run_id}: parameter "
                    f"{name!r} stored={stored.params[name]!r} != "
                    f"new={given[name]!r}"
                )


def check_param_order(store, param_ranges) -> None:
    """Validate that ``param_ranges`` keys, in order, match the stored parameters.

    Every algorithm iterates ``list(param_ranges)`` in insertion order, so a
    reordered ``param_ranges`` changes the RNG draw sequence even when the
    key *set* is unchanged.  ``store`` is an opened ``SessionStore`` (or any
    object exposing ``param_names``).
    """
    given = list(param_ranges)
    stored = list(store.param_names)
    if given != stored:
        raise ValueError(
            f"parameter order mismatch: param_ranges lists {given!r} but the "
            f"session stores {stored!r}."
        )
