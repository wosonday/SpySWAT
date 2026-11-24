"""Slot scheduler for ``ScenarioBatch.run``: one pool, a pending job queue.

Pure bookkeeping — no filesystem or process access. It decides which pending job
goes to which free slot and whether that slot must be reseeded (re-copied from the
job's base TxtInOut). The parent drives it as futures complete.
"""
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .model import Job


@dataclass
class Slot:
    """One worker folder slot.

    ``base`` is the base TxtInOut the slot currently holds (``None`` before its
    first job). ``needs_reseed`` forces a re-copy before the next job (fresh slot
    or a job that failed). ``unusable`` means the folder could not be removed and
    the slot must never be reused.
    """
    base: Optional[str] = None
    needs_reseed: bool = False
    unusable: bool = False


class Scheduler:
    """Dispatch the pending jobs (plan order) onto a fixed set of slots."""

    def __init__(self, jobs: List[Job], base_of: Callable[[Job], str], n_slots: int):
        if n_slots < 1:
            raise ValueError("n_slots must be >= 1")
        self._pending: List[Job] = list(jobs)
        self._base_of = base_of
        self.slots: List[Slot] = [Slot() for _ in range(n_slots)]
        self._bad_bases = set()

    # -- queries ---------------------------------------------------------

    @property
    def pending(self) -> List[Job]:
        return list(self._pending)

    def has_pending(self) -> bool:
        return bool(self._pending)

    def all_slots_unusable(self) -> bool:
        return bool(self.slots) and all(s.unusable for s in self.slots)

    def is_base_bad(self, base: str) -> bool:
        return base in self._bad_bases

    # -- mutations -------------------------------------------------------

    def take(self, slot_idx: int) -> Tuple[Optional[Job], bool]:
        """Pop the next job for a free slot; return ``(job, reseed)``.

        Prefers a pending job whose base matches the slot's current base (no
        reseed). Otherwise takes the first pending job of any base and reseeds the
        slot for that base. Returns ``(None, False)`` when the slot is unusable or
        nothing is pending.
        """
        slot = self.slots[slot_idx]
        if slot.unusable or not self._pending:
            return None, False
        if not slot.needs_reseed and slot.base is not None:
            for i, job in enumerate(self._pending):
                if self._base_of(job) == slot.base:
                    self._pending.pop(i)
                    return job, False
        job = self._pending.pop(0)
        slot.base = self._base_of(job)
        return job, True

    def finish(self, slot_idx: int, ok: bool) -> None:
        """Record a completed job; a failure forces a reseed before the next job."""
        self.slots[slot_idx].needs_reseed = not ok

    def mark_slot_unusable(self, slot_idx: int) -> None:
        self.slots[slot_idx].unusable = True

    def mark_base_bad(self, base: str) -> None:
        self._bad_bases.add(base)

    def drain_bad_base_jobs(self) -> List[Job]:
        """Remove and return every pending job whose base is bad."""
        drained = [j for j in self._pending if self._base_of(j) in self._bad_bases]
        self._pending = [j for j in self._pending if self._base_of(j) not in self._bad_bases]
        return drained

    def drain_all_pending(self) -> List[Job]:
        jobs = list(self._pending)
        self._pending.clear()
        return jobs
