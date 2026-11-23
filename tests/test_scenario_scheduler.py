"""Unit tests for the ScenarioBatch slot scheduler (pure dispatch bookkeeping)."""
import pytest

from spyswat.swat_calib.scenarios.model import Job, ParamSet, Scenario
from spyswat.swat_calib.scenarios.scheduler import Scheduler, Slot


def _jobs(names):
    return [Job(Scenario(n), ParamSet("p")) for n in names]


def _base_of(base_map):
    return lambda j: base_map[j.job_id]


def test_n_slots_must_be_positive():
    with pytest.raises(ValueError):
        Scheduler([], _base_of({}), 0)


def test_fresh_slot_reseeds_first_job():
    jobs = _jobs(["a1", "a2"])
    s = Scheduler(jobs, _base_of({"a1__p": "A", "a2__p": "A"}), n_slots=1)
    j, reseed = s.take(0)
    assert (j.job_id, reseed) == ("a1__p", True)
    assert s.slots[0].base == "A"


def test_prefers_same_base_over_reseed():
    jobs = _jobs(["a1", "b1", "a2"])
    base = {"a1__p": "A", "b1__p": "B", "a2__p": "A"}
    s = Scheduler(jobs, _base_of(base), n_slots=1)
    j, reseed = s.take(0)
    assert (j.job_id, reseed) == ("a1__p", True)   # fresh slot -> reseed A
    s.finish(0, ok=True)
    # slot holds A; pending [b1, a2] -> prefer a2 (same base), no reseed
    j, reseed = s.take(0)
    assert (j.job_id, reseed) == ("a2__p", False)
    s.finish(0, ok=True)
    # only b1 left -> switch A -> B, reseed
    j, reseed = s.take(0)
    assert (j.job_id, reseed) == ("b1__p", True)
    assert s.slots[0].base == "B"


def test_failed_job_forces_reseed_of_same_base():
    jobs = _jobs(["a1", "a2"])
    s = Scheduler(jobs, _base_of({"a1__p": "A", "a2__p": "A"}), n_slots=1)
    j, reseed = s.take(0)
    assert (j.job_id, reseed) == ("a1__p", True)
    s.finish(0, ok=False)                            # failure
    j, reseed = s.take(0)
    assert (j.job_id, reseed) == ("a2__p", True)     # same base but forced reseed


def test_unusable_slot_yields_nothing():
    jobs = _jobs(["a1"])
    s = Scheduler(jobs, _base_of({"a1__p": "A"}), n_slots=1)
    s.mark_slot_unusable(0)
    assert s.take(0) == (None, False)
    assert s.all_slots_unusable()
    assert s.has_pending()


def test_bad_base_drains_its_pending_jobs():
    jobs = _jobs(["a1", "b1", "b2", "a2"])
    base = {"a1__p": "A", "b1__p": "B", "b2__p": "B", "a2__p": "A"}
    s = Scheduler(jobs, _base_of(base), n_slots=1)
    s.mark_base_bad("B")
    assert s.is_base_bad("B") and not s.is_base_bad("A")
    drained = s.drain_bad_base_jobs()
    assert [j.job_id for j in drained] == ["b1__p", "b2__p"]
    assert [j.job_id for j in s.pending] == ["a1__p", "a2__p"]


def test_drain_all_pending():
    jobs = _jobs(["a1", "b1"])
    s = Scheduler(jobs, _base_of({"a1__p": "A", "b1__p": "B"}), n_slots=2)
    rest = s.drain_all_pending()
    assert [j.job_id for j in rest] == ["a1__p", "b1__p"]
    assert not s.has_pending()
