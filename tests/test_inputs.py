"""Tests for reading/writing SWAT input (TxtInOut) files. All fixtures are synthetic."""
import os
import stat
from pathlib import Path

import pandas as pd
import pytest

from spyswat.swat_calib.core.hru_manager import HRUManager
from spyswat.swat_calib.core.txinout import TxInOut
from spyswat.swat_calib.io import writers
from spyswat.swat_calib.io.file_cio import FileCIO
from spyswat.swat_calib.io.parameters import SWATParam
from spyswat.swat_calib.io.writers import HRUWriter, SWATFileFormatError, atomic_write_lines
from spyswat.swat_calib.utils.param_loader import load_param_ranges

CRLF = "\r\n"

PARAM_TXT = """! test parameter file
!Parameter AtLine Start End Round Min Max
ALPHA_BF.gw   2   1   16   4   0.0    1.0
GWQMN.gw      3   1   16   4   0.0    5000.0
CN2.mgt       2   1   16   2   35.0   98.0
SOL_ZMX.sol   2  29   36   2   0.0    3500.0
SOL_Z.sol     3  28   39   2   0.0    3500.0
SOL_BD.sol    4  28   39   2   0.9    2.5
SFTMP.bsn     2   1   16   3  -20.0   20.0
SMTMP.bsn     3   1   16   3  -20.0   20.0
SMFMX.bsn     4   1   16   3   0.0    20.0
"""


def _hru_header(sub, hru, ws):
    return (f" .hru file Watershed HRU:{ws} Subbasin:{sub} HRU:{hru} Luse:AGRL "
            f"Soil: Ao90-2-3c-4284 Slope: 10-20 9/30/2025 12:00:00 AM ArcSWAT")


def _sol_lines(nl=CRLF):
    lab = lambda s: s.ljust(27)[:27]
    f = lambda *v: "".join(f"{x:12.2f}" for x in v)
    return [
        " .Sol file Watershed HRU:1" + nl,
        " Maximum rooting depth(mm) :  420.00" + nl,
        lab(" Depth                [mm]:") + f(300.0, 1000.0, 1500.0) + nl,
        lab(" Bulk Density Moist [g/cc]:") + f(1.50, 1.60, 1.70) + nl,
        lab(" Ave. AW Incl. Rock Frag  :") + f(0.10, 0.11, 0.12) + nl,
    ]


def _gw_lines(nl=CRLF):
    return [" .gw file" + nl,
            f"{0.5:16.4f}    | ALPHA_BF : Baseflow alpha factor" + nl,
            f"{750.0:16.4f}    | GWQMN : Threshold depth" + nl]


def _mgt_lines(nl=CRLF):
    return [" .mgt file" + nl, f"{78.0:16.2f}    | CN2: Initial SCS CN II value" + nl]


def _bsn_lines(nl=CRLF):
    return ["Basin data           .bsn file" + nl,
            f"{1.0:16.3f}    | SFTMP : Snowfall temperature [º" + "C]" + nl,
            f"{0.5:16.3f}    | SMTMP : Snow melt base temperature" + nl,
            f"{4.5:16.3f}    | SMFMX : Melt factor" + nl]


def _write(path: Path, lines, encoding="utf-8"):
    with open(path, "w", encoding=encoding, newline="") as f:
        f.writelines(lines)


def _read_bytes(path: Path) -> bytes:
    return Path(path).read_bytes()


def build_txinout(root: Path, nl=CRLF):
    """3 HRUs: 000010001, 000010002 (subbasin 1) and 000020001 (subbasin 2)."""
    root.mkdir(parents=True, exist_ok=True)
    ids = [(1, 1, 1), (1, 2, 2), (2, 1, 3)]
    for sub, hru, ws in ids:
        stem = f"{sub:05d}{hru:04d}"
        _write(root / f"{stem}.hru", [_hru_header(sub, hru, ws) + nl, f"{0.1:16.7f}    | HRU_FR" + nl])
        _write(root / f"{stem}.sol", _sol_lines(nl))
        _write(root / f"{stem}.gw", _gw_lines(nl))
        _write(root / f"{stem}.mgt", _mgt_lines(nl))
    _write(root / "basins.bsn", _bsn_lines(nl), encoding="utf-8")
    return root


@pytest.fixture
def param_file(tmp_path):
    p = tmp_path / "swatParam.txt"
    p.write_text(PARAM_TXT, encoding="utf-8")
    return p


@pytest.fixture
def env(tmp_path, param_file):
    root = build_txinout(tmp_path / "TxtInOut")
    tx = TxInOut(root)
    mgr = HRUManager(tx, SWATParam(param_file))
    return root, tx, mgr


def snapshot(root: Path):
    return {p.name: _read_bytes(p) for p in sorted(root.iterdir()) if p.is_file()}


# ------------------------------------------------------------------ round trip
@pytest.mark.parametrize("nl", ["\r\n", "\n"])
def test_noop_roundtrip_is_byte_identical(tmp_path, nl):
    root = build_txinout(tmp_path / "t", nl)
    before = snapshot(root)
    for name in ("000010001.sol", "000010001.gw", "000010001.mgt", "basins.bsn"):
        w = HRUWriter(root / name)
        assert w.save() is False                       # nothing changed -> not written
        atomic_write_lines(root / name, w.lines)       # forced rewrite: still identical
    assert snapshot(root) == before
    assert "º".encode("utf-8") in before["basins.bsn"]


def test_roundtrip_latin1_encoded_degree_sign(tmp_path):
    p = tmp_path / "basins.bsn"
    raw = "x [ºC]\r\n   1.000    | SFTMP\r\n".encode("latin-1")
    p.write_bytes(raw)
    w = HRUWriter(p)
    atomic_write_lines(p, w.lines)
    assert p.read_bytes() == raw


def test_change_preserves_terminators_and_other_lines(env):
    root, _, mgr = env
    before = _read_bytes(root / "basins.bsn")
    mgr.update_params({"SFTMP.bsn": (2.0, "replace")})
    after = _read_bytes(root / "basins.bsn")
    assert after.count(b"\r\n") == before.count(b"\r\n") == 4
    assert after.splitlines()[0] == before.splitlines()[0]
    assert after.splitlines()[1] != before.splitlines()[1]
    assert "º".encode("utf-8") in after


# ------------------------------------------------------------------ strict writer
def _bytes_unchanged_after_error(root, mgr, params, match=None):
    before = snapshot(root)
    with pytest.raises(ValueError, match=match):
        mgr.update_params(params)
    assert snapshot(root) == before
    assert not [p for p in root.iterdir() if p.name.endswith(".tmp")]


def test_error_line_does_not_exist(env):
    root, tx, mgr = env
    # a short file: only the header
    _write(root / "000010002.gw", [" .gw file" + CRLF])
    _bytes_unchanged_after_error(root, mgr, {"ALPHA_BF.gw": (0.2, "replace")},
                                 match=r"000010002\.gw, line 2, parameter ALPHA_BF.*does not exist")


def test_error_line_too_short(env):
    root, _, mgr = env
    _write(root / "000010001.gw", [" .gw file" + CRLF, "   0.5" + CRLF, "x" + CRLF])
    _bytes_unchanged_after_error(root, mgr, {"ALPHA_BF.gw": (0.2, "replace")},
                                 match=r"line 2.*shorter than the field end")


def test_short_last_line_without_newline_is_still_an_error_not_a_merge(env):
    root, _, mgr = env
    _write(root / "000010001.mgt", [" .mgt file" + CRLF, "   78.0"])
    _bytes_unchanged_after_error(root, mgr, {"CN2.mgt": (50.0, "replace")}, match="shorter")


def test_error_old_value_unparseable_for_relative_but_not_for_replace(env):
    root, _, mgr = env
    bad = [" .mgt file" + CRLF, "         abcdef    | CN2" + CRLF]
    _write(root / "000010001.mgt", bad)
    _bytes_unchanged_after_error(root, mgr, {"CN2.mgt": (0.1, "relative")},
                                 match=r"old value cannot be parsed.*'")
    _bytes_unchanged_after_error(root, mgr, {"CN2.mgt": (0.1, "add")}, match="cannot be parsed")
    mgr.update_params({"CN2.mgt": (60.0, "replace")})        # replace needs no old value
    assert "60.00" in (root / "000010001.mgt").read_text(encoding="latin-1")


def test_error_new_value_wider_than_field(env):
    root, _, mgr = env
    # GWQMN has vmax 5000 -> clamp; use ALPHA_BF with a huge vmax through a param file instead
    pf = root.parent / "wide.txt"
    pf.write_text("GWQMN.gw 3 1 16 4 0.0 1e30\n", encoding="utf-8")
    mgr2 = HRUManager(mgr.txinout, SWATParam(pf))
    _bytes_unchanged_after_error(root, mgr2, {"GWQMN.gw": (1e20, "replace")}, match="wider than")


def test_error_non_finite_value(env):
    root, _, mgr = env
    _bytes_unchanged_after_error(root, mgr, {"CN2.mgt": (float("nan"), "replace")}, match="not finite")


def test_error_sol_data_not_multiple_of_12(env):
    root, _, mgr = env
    lines = _sol_lines()
    lines[3] = lines[3].replace("        1.60", "       1.60")   # one char short
    _write(root / "000010001.sol", lines)
    _bytes_unchanged_after_error(root, mgr, {"SOL_BD.sol": (1.5, "replace")},
                                 match=r"000010001\.sol, line 4.*not a multiple of 12")


def test_error_sol_field_not_right_aligned(env):
    root, _, mgr = env
    lines = _sol_lines()
    lines[3] = lines[3][:-14] + "       1.70 " + CRLF         # trailing blank, same length
    _write(root / "000010001.sol", lines)
    _bytes_unchanged_after_error(root, mgr, {"SOL_BD.sol": (1.5, "replace")},
                                 match="not right-aligned")


def test_error_sol_field_not_numeric(env):
    root, _, mgr = env
    lines = _sol_lines()
    lines[2] = lines[2][:27] + "        abcd" + lines[2][39:]
    _write(root / "000010001.sol", lines)
    _bytes_unchanged_after_error(root, mgr, {"SOL_Z.sol": (500.0, "replace")}, match="not a number")


def test_invalid_file_blocks_every_other_write(env):
    root, _, mgr = env
    _write(root / "000020001.gw", [" .gw file" + CRLF])         # last file is bad
    _bytes_unchanged_after_error(root, mgr, {"ALPHA_BF.gw": (0.2, "replace"),
                                             "CN2.mgt": (60.0, "replace"),
                                             "SFTMP.bsn": (2.0, "replace")})


def test_unknown_method_rejected(env):
    root, _, mgr = env
    _bytes_unchanged_after_error(root, mgr, {"CN2.mgt": (1.0, "multiply")}, match="Method")


def test_method_aliases(env):
    root, _, mgr = env
    mgr.update_params({"CN2.mgt": (0.1, "r")})                   # 78 * 1.1
    assert float((root / "000010001.mgt").read_text(encoding="latin-1").splitlines()[1][:16]) == pytest.approx(85.8)
    mgr.update_params({"CN2.mgt": (-5.0, "a")})                  # alias for add
    assert float((root / "000010001.mgt").read_text(encoding="latin-1").splitlines()[1][:16]) == pytest.approx(80.8)
    mgr.update_params({"CN2.mgt": (70.0, "v")})
    assert float((root / "000010001.mgt").read_text(encoding="latin-1").splitlines()[1][:16]) == pytest.approx(70.0)
    mgr.update_params({"CN2.mgt": (71.0, "Replace")})
    assert float((root / "000010001.mgt").read_text(encoding="latin-1").splitlines()[1][:16]) == pytest.approx(71.0)


def test_clamp_to_vmin_vmax(env):
    root, _, mgr = env
    mgr.update_params({"CN2.mgt": (500.0, "replace")})
    assert float((root / "000010001.mgt").read_text(encoding="latin-1").splitlines()[1][:16]) == 98.0


def test_sol_layers_and_positional_sol(env):
    root, _, mgr = env
    mgr.update_params({"SOL_BD.sol": (0.1, "relative"), "SOL_ZMX.sol": (500.0, "replace")})
    with open(root / "000010001.sol", encoding="latin-1", newline="") as fh:
        lines = fh.read().split(CRLF)
    assert lines[3][27:] == "".join(f"{x:12.2f}" for x in (1.65, 1.76, 1.87))
    assert lines[1].endswith("  500.00") or lines[1][28:36].strip() == "500.00"
    assert len(lines[3]) == 27 + 36


# ------------------------------------------------------------------ one write per file
def test_each_file_written_once_and_shape_unchanged(env, monkeypatch):
    root, _, mgr = env
    before = {n: b.decode("latin-1", errors="strict").split("\n") for n, b in snapshot(root).items()}
    calls = []
    real = os.replace

    def counting(src, dst):
        calls.append(Path(dst).name)
        return real(src, dst)

    monkeypatch.setattr(writers.os, "replace", counting)
    mgr.update_params({
        "SFTMP.bsn": (2.0, "replace"),
        "SMTMP.bsn": (0.25, "add"),
        "SMFMX.bsn": (0.1, "relative"),
        "CN2.mgt": [(0.1, "relative"), (-3.0, "add")],
        "ALPHA_BF.gw": (0.3, "replace"),
        "GWQMN.gw": (0.1, "r"),
        "SOL_BD.sol": (0.01, "add"),
    })
    assert len(calls) == len(set(calls))
    assert set(calls) == {"basins.bsn", "000010001.mgt", "000010002.mgt", "000020001.mgt",
                          "000010001.gw", "000010002.gw", "000020001.gw",
                          "000010001.sol", "000010002.sol", "000020001.sol"}
    after = {n: b.decode("latin-1").split("\n") for n, b in snapshot(root).items()}
    for name, old in before.items():
        assert len(after[name]) == len(old)
        assert [len(x) for x in after[name]] == [len(x) for x in old]
    bsn = (root / "basins.bsn").read_text(encoding="latin-1").splitlines()
    assert float(bsn[1][:16]) == pytest.approx(2.0)
    assert float(bsn[2][:16]) == pytest.approx(0.75)
    assert float(bsn[3][:16]) == pytest.approx(4.95)
    # two passes on CN2 applied in order: 78*1.1 - 3
    assert float((root / "000010001.mgt").read_text(encoding="latin-1").splitlines()[1][:16]) == pytest.approx(82.8)


def test_subbasin_filter(env):
    root, _, mgr = env
    mgr.update_params({"ALPHA_BF.gw": (0.9, "replace")}, subbasin=2)
    val = lambda n: float((root / n).read_text(encoding="latin-1").splitlines()[1][:16])
    assert val("000020001.gw") == pytest.approx(0.9)
    assert val("000010001.gw") == pytest.approx(0.5)
    mgr.update_params({"ALPHA_BF.gw": [(0.7, "replace", 1)]})
    assert val("000010002.gw") == pytest.approx(0.7)
    assert val("000020001.gw") == pytest.approx(0.9)


def test_update_by_df_single_pass(env, monkeypatch):
    root, _, mgr = env
    calls = []
    real = os.replace
    monkeypatch.setattr(writers.os, "replace", lambda s, d: (calls.append(Path(d).name), real(s, d))[1])
    df = pd.DataFrame({"param": ["SFTMP.bsn", "SMTMP.bsn", "ALPHA_BF.gw"],
                       "method": ["replace", "a", "r"], "value": [3.0, 1.0, 0.5],
                       "subbasin": ["All", "All", "1,2"]})
    mgr.update_by_df(df)
    assert calls.count("basins.bsn") == 1
    assert len(calls) == len(set(calls))
    assert float((root / "000020001.gw").read_text(encoding="latin-1").splitlines()[1][:16]) == pytest.approx(0.75)


def test_read_only_file_is_updated_and_stays_read_only(env, monkeypatch):
    root, _, mgr = env
    f = root / "000010001.mgt"
    os.chmod(f, stat.S_IREAD)
    real = os.replace

    def windows_like(src, dst):
        # Windows refuses to replace a read-only destination
        if not os.access(dst, os.W_OK) and os.geteuid() != 0 if hasattr(os, "geteuid") else False:
            raise PermissionError(13, "read-only destination", str(dst))
        return real(src, dst)

    monkeypatch.setattr(writers.os, "replace", windows_like)
    try:
        mgr.update_params({"CN2.mgt": (60.0, "replace")}, subbasin=1)
        assert "60.00" in f.read_text(encoding="latin-1")
        assert not os.access(f, os.W_OK) or os.name == "nt" or os.geteuid() == 0  # mode restored
    finally:
        os.chmod(f, stat.S_IREAD | stat.S_IWRITE)


def test_replace_failure_leaves_no_temp_file_and_original_intact(env, monkeypatch):
    root, _, mgr = env
    before = snapshot(root)

    def failing(src, dst):
        raise PermissionError(13, "locked", str(dst))

    monkeypatch.setattr(writers.os, "replace", failing)
    monkeypatch.setattr(writers.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        mgr.update_params({"CN2.mgt": (60.0, "replace")}, subbasin=1)
    monkeypatch.undo()
    assert snapshot(root) == before
    assert not [p for p in root.iterdir() if p.name.endswith(".tmp")]


def test_replace_failure_on_read_only_original_restores_mode(env, monkeypatch):
    root, _, mgr = env
    f = root / "000010001.mgt"
    os.chmod(f, stat.S_IREAD)
    try:
        monkeypatch.setattr(writers.os, "replace",
                            lambda s, d: (_ for _ in ()).throw(PermissionError(13, "locked")))
        monkeypatch.setattr(writers.time, "sleep", lambda s: None)
        with pytest.raises(PermissionError):
            mgr.update_params({"CN2.mgt": (60.0, "replace")}, subbasin=1)
        monkeypatch.undo()
        assert stat.S_IMODE(os.stat(f).st_mode) & stat.S_IWRITE == 0 or os.name == "nt" or os.geteuid() == 0
        assert not [p for p in root.iterdir() if p.name.endswith(".tmp")]
    finally:
        os.chmod(f, stat.S_IREAD | stat.S_IWRITE)


def test_unknown_parameter_raises_keyerror_before_any_write(env):
    root, _, mgr = env
    before = snapshot(root)
    with pytest.raises(KeyError, match="CN3.mgt"):
        mgr.update_params({"SFTMP.bsn": (2.0, "replace"), "CN3.mgt": (1.0, "replace")})
    assert snapshot(root) == before
    df = pd.DataFrame({"param": ["SFTMP.bsn", "NOPE.gw"], "method": ["replace"] * 2, "value": [1.0, 1.0]})
    with pytest.raises(KeyError, match="NOPE.gw"):
        mgr.update_by_df(df)
    assert snapshot(root) == before


def test_save_shape_check_is_not_an_assert(env):
    root, _, _ = env
    w = HRUWriter(root / "000010001.mgt")
    before = _read_bytes(root / "000010001.mgt")
    w.lines[1] = w.lines[1][:-5] + "\r\n"
    with pytest.raises(SWATFileFormatError, match="length"):
        w.save()
    w.lines = w.lines[:1]
    with pytest.raises(SWATFileFormatError, match="line count"):
        w.save()
    assert _read_bytes(root / "000010001.mgt") == before


# ------------------------------------------------------------------ validate_inputs
def test_validate_inputs_healthy_and_damaged(env):
    root, _, mgr = env
    df = mgr.validate_inputs()
    assert list(df.columns)[:5] == ["file", "param", "line", "problem", "text"]
    assert df.empty, df
    before = snapshot(root)
    lines = _sol_lines()
    lines[3] = lines[3].replace("        1.50", "        1.5 ")     # blank before... right edge shifted
    lines[3] = lines[3][:27] + "       1.50 " + lines[3][39:]      # right-aligned broken (same length)
    _write(root / "000010002.sol", lines)
    before = snapshot(root)
    df = mgr.validate_inputs(["SOL_BD.sol", "SOL_Z.sol", "CN2.mgt"])
    assert set(df.file) == {"000010002.sol"}
    assert (df.param == "SOL_BD.sol").all() and (df.line == 4).all()
    assert df.problem.str.contains("misalignment").any()
    assert snapshot(root) == before


def test_validate_inputs_other_problems(env):
    root, _, mgr = env
    _write(root / "000010001.gw", [" .gw file" + CRLF, "   0.5" + CRLF])
    _write(root / "000010002.mgt", [" .mgt file" + CRLF, f"{250.0:16.2f}    | CN2" + CRLF])
    _write(root / "000020001.gw", [" .gw file" + CRLF, "  abc" + " " * 11 + "    | A" + CRLF,
                                   "x" * 30 + CRLF])
    df = mgr.validate_inputs(["ALPHA_BF.gw", "GWQMN.gw", "CN2.mgt"])
    probs = {(r.file, r.param): r.problem for r in df.itertuples()}
    assert "too short" in probs[("000010001.gw", "ALPHA_BF.gw")]
    assert "line missing" in probs[("000010001.gw", "GWQMN.gw")]
    assert "out of range" in probs[("000010002.mgt", "CN2.mgt")]
    assert "not numeric" in probs[("000020001.gw", "ALPHA_BF.gw")]


# ------------------------------------------------------------------ param loader
def test_load_param_ranges_name_key_and_errors(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("name,method,min,max,subbasin\nCN2.mgt,relative,-0.2,0.2,All\n"
                 "ALPHA_BF.gw,a,0,1,\"1, 2\"\n", encoding="utf-8")
    r = load_param_ranges(str(a))
    assert r["CN2.mgt"] == ((-0.2, 0.2), "relative")
    assert r["ALPHA_BF.gw"] == ((0.0, 1.0), "a", [1, 2])

    b = tmp_path / "b.csv"
    b.write_text("key,method,min,max\nCN2.mgt,r,-0.1,0.1\n", encoding="utf-8")
    assert load_param_ranges(str(b))["CN2.mgt"] == ((-0.1, 0.1), "r")

    c = tmp_path / "c.csv"
    c.write_text("key,name,method,min,max\nCN2.mgt,WRONG,r,-0.1,0.1\n", encoding="utf-8")
    assert list(load_param_ranges(str(c))) == ["CN2.mgt"]

    d = tmp_path / "d.csv"
    d.write_text("param,method,min,max\nCN2.mgt,r,-0.1,0.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="key"):
        load_param_ranges(str(d))


# ------------------------------------------------------------------ TxInOut
def test_number_hru_and_sub(env):
    _, tx, _ = env
    assert tx.number_hru == 3
    assert tx.number_sub == 2
    assert len(tx.hru_info) == 3


def test_bad_hru_header_raises_with_file_name(tmp_path):
    root = build_txinout(tmp_path / "t")
    _write(root / "000010002.hru", ["this is not a header" + CRLF])
    with pytest.raises(ValueError, match=r"000010002\.hru.*this is not a header"):
        TxInOut(root)


def test_empty_hru_file_raises_value_error(tmp_path):
    root = build_txinout(tmp_path / "t")
    (root / "000010002.hru").write_bytes(b"")
    with pytest.raises(ValueError, match=r"000010002\.hru"):
        TxInOut(root)


# ------------------------------------------------------------------ FileCIO
def _cio_lines(nl=CRLF, iprint=1):
    lines = [f"line {i}{nl}" for i in range(70)]
    put = lambda i, v, label: lines.__setitem__(i, f"{v:16d}    | {label}{nl}")
    put(7, 22, "NBYR : Number of years simulated")
    put(8, 1998, "IYR : Beginning year of simulation")
    put(9, 1, "IDAF : Beginning julian day")
    put(10, 365, "IDAL : Ending julian day")
    put(58, iprint, "IPRINT: print code (month, day, year)")
    put(59, 2, "NYSKIP: number of years to skip")
    return lines


def _cio_env(tmp_path, iprint=1, pcp_years=(1998, 1999, 2000)):
    root = tmp_path / "cio"
    root.mkdir()
    _write(root / "file.cio", _cio_lines(iprint=iprint))
    rows = [f"{y}{d:03d}   0.0{CRLF}" for y in pcp_years for d in range(1, 4)]
    _write(root / "pcp1.pcp", ["Station x" + CRLF, "Lati 1" + CRLF, "Long 1" + CRLF, "Elev 1" + CRLF] + rows)
    return root, TxInOut(root)


def test_fileCIO_set_and_get_iprint(tmp_path):
    root, tx = _cio_env(tmp_path)
    cio = FileCIO(tx)
    assert (cio.begin_year, cio.year_start, cio.year_end) == (1998, 2000, 2019)
    assert cio.get_iprint() == "D"
    cio.set(NBYR=10, IYR=2001, IDAF=5, IDAL=300, IPRINT=0, NYSKIP=1)
    assert cio.get_iprint() == "MS"
    assert (cio.begin_year, cio.year_start, cio.year_end) == (2001, 2002, 2010)
    raw = (root / "file.cio").read_bytes().split(b"\r\n")
    orig = [l.encode() for l in _cio_lines()]
    assert len(raw) == 71 and [len(x) for x in raw[:70]] == [len(x) - 2 for x in orig]  # shape unchanged
    fresh = FileCIO(TxInOut(root))
    assert (fresh.begin_year, fresh.year_start, fresh.year_end) == (2001, 2002, 2010)
    assert fresh.get_iprint() == "MS"
    cio.set_iprint("YS")
    assert cio.get_iprint() == "YS"
    cio.set_year_skip(0)
    assert cio.year_start == 2001


def test_fileCIO_set_rejects_bad_input(tmp_path):
    root, tx = _cio_env(tmp_path)
    cio = FileCIO(tx)
    before = _read_bytes(root / "file.cio")
    for bad in ({"FOO": 1}, {"NBYR": 1.5}, {"NBYR": "3"}, {"IPRINT": 7}, {"NBYR": -1}, {"IYR": 12345}):
        with pytest.raises(ValueError):
            cio.set(**bad)
    assert _read_bytes(root / "file.cio") == before


def test_fileCIO_unknown_iprint(tmp_path):
    root, tx = _cio_env(tmp_path, iprint=7)
    with pytest.raises(ValueError, match="IPRINT"):
        FileCIO(tx).get_iprint()


def test_fileCIO_update_from_pcp_single_year(tmp_path):
    root, tx = _cio_env(tmp_path, pcp_years=(2005,))
    cio = FileCIO(tx)
    cio.update()
    assert cio.begin_year == 2005
    assert cio.year_end == 2005
    text = (root / "file.cio").read_text(encoding="latin-1")
    assert "   1" in text.splitlines()[7]
