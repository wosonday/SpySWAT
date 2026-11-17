"""Tests for reading SWAT output files (OutputFileManager) on synthetic fixtures."""
import os
from pathlib import Path

import numpy as np
import pytest

from spyswat.swat_calib.core.output_manager import OutputFileManager
from spyswat.swat_calib.utils.output_mapping_info import ReachMapping, SedimentMapping

RCH_LEN = 590
RCH_HEADER = 9


class FakeTxInOut:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def get_watershed_file(self, ext):
        assert ext == '.cio'
        return self.directory / 'file.cio'

    def get_output_file(self, ext):
        return self.directory / {'.rch': 'output.rch', '.sed': 'output.sed'}[ext]


def write_cio(directory: Path, iprint: int, nbyr: int = 5, iyr: int = 2000, skip: int = 0):
    lines = [f"{'':16}    | filler {i}\n" for i in range(85)]
    lines[7] = f"{nbyr:16d}    | NBYR\n"
    lines[8] = f"{iyr:16d}    | IYR\n"
    lines[58] = f"{iprint:16d}    | IPRINT\n"
    lines[59] = f"{skip:16d}    | NYSKIP\n"
    (directory / 'file.cio').write_text(''.join(lines))


def _put(buf: bytearray, colspec, text: str):
    start, end = colspec
    text = text[-(end - start):].rjust(end - start)
    buf[start:end] = text.encode()


def rch_line(rch: int, mon: float, flow_out: float, sed_out: float = 1.0) -> str:
    buf = bytearray(b' ' * RCH_LEN)
    buf[0:5] = b'REACH'
    for name, info in ReachMapping.get_mapping().items():
        _put(buf, info['colspec'], '0.0000E+00')
    _put(buf, ReachMapping.get_colspec('RCH'), str(rch))
    _put(buf, ReachMapping.get_colspec('MON'), f"{mon:g}")
    _put(buf, ReachMapping.get_colspec('FLOW_OUTcms'), f"{flow_out:.4E}")
    _put(buf, ReachMapping.get_colspec('SED_OUTtons'), f"{sed_out:.4E}")
    return buf.decode()


def write_rch(path: Path, rows, eol: str = '\r\n'):
    head = ['1'] + [''] * (RCH_HEADER - 1)
    with open(path, 'w', newline='') as f:
        for h in head:
            f.write(h + eol)
        for r in rows:
            f.write(r + eol)


def daily_rows(n_reaches: int, days: int, base: float = 1.0):
    # flow encodes (reach, day) so that order is checkable
    return [rch_line(r, d, base * (r * 1000 + d)) for d in range(1, days + 1)
            for r in range(1, n_reaches + 1)]


def monthly_rows(n_reaches: int, years: int, first_year: int = 2000):
    """12 monthly blocks + annual block (MON=year) per year, then average-annual block."""
    rows = []
    for y in range(years):
        for m in range(1, 13):
            rows += [rch_line(r, m, y * 100 + m + r / 10) for r in range(1, n_reaches + 1)]
        rows += [rch_line(r, first_year + y, -1.0) for r in range(1, n_reaches + 1)]
    rows += [rch_line(r, years, -2.0) for r in range(1, n_reaches + 1)]
    return rows


@pytest.fixture
def env(tmp_path):
    write_cio(tmp_path, iprint=1)
    return tmp_path, FakeTxInOut(tmp_path)


# ---------------------------------------------------------------- cache
def test_stale_cache_equal_size_rewrite(env):
    d, tx = env
    rch = d / 'output.rch'
    write_rch(rch, daily_rows(2, 3, base=1.0))
    mgr = OutputFileManager(tx)
    first = mgr.read_rch(columns='FLOW_OUTcms')
    size = rch.stat().st_size
    old = rch.stat().st_mtime_ns

    write_rch(rch, daily_rows(2, 3, base=2.0))
    assert rch.stat().st_size == size
    os.utime(rch, ns=(old + 5_000_000_000, old + 5_000_000_000))

    second = mgr.read_rch(columns='FLOW_OUTcms')
    assert second['FLOW_OUTcms'].iloc[0] == pytest.approx(2 * first['FLOW_OUTcms'].iloc[0])
    assert len(mgr._cache.keys()) == 1


def test_unchanged_file_served_from_cache_and_invalidate(env):
    d, tx = env
    rch = d / 'output.rch'
    write_rch(rch, daily_rows(2, 3))
    mgr = OutputFileManager(tx)
    mgr.read_rch()
    mgr.read_rch(columns='FLOW_OUTcms')
    assert len(mgr._cache.keys()) == 2
    mgr.invalidate()
    assert len(mgr._cache.keys()) == 0
    assert mgr.read_rch(columns='FLOW_OUTcms')['RCH'].iloc[0] == 1


def test_cache_returns_copies(env):
    d, tx = env
    write_rch(d / 'output.rch', daily_rows(2, 3))
    mgr = OutputFileManager(tx)
    a = mgr.read_rch(columns='FLOW_OUTcms')
    a.loc[:, 'FLOW_OUTcms'] = -5
    b = mgr.read_rch(columns='FLOW_OUTcms')
    assert (b['FLOW_OUTcms'] > 0).all()


# ---------------------------------------------------------------- frequency
def test_daily_autodetect_all_rows_in_file_order(env):
    d, tx = env
    write_rch(d / 'output.rch', daily_rows(3, 400))  # MON up to 400 must not be filtered
    df = OutputFileManager(tx).read_rch(columns='FLOW_OUTcms')
    assert len(df) == 3 * 400
    expected = [r * 1000 + dd for dd in range(1, 401) for r in range(1, 4)]
    assert df['FLOW_OUTcms'].tolist() == pytest.approx(expected, rel=1e-4)
    sub = OutputFileManager(tx).read_rch(columns='FLOW_OUTcms', reach_id=2, freq='D')
    assert sub['RCH'].eq(2).all() and len(sub) == 400


@pytest.mark.parametrize('iprint, freq', [(1, 'MS'), (1, 'YS'), (0, 'D'), (0, 'YS')])
def test_explicit_freq_mismatch_raises(tmp_path, iprint, freq):
    write_cio(tmp_path, iprint=iprint)
    write_rch(tmp_path / 'output.rch', daily_rows(2, 2))
    with pytest.raises(ValueError, match="contradicts"):
        OutputFileManager(FakeTxInOut(tmp_path)).read_rch(freq=freq)


def test_iprint_read_fresh_every_call(env):
    d, tx = env
    write_rch(d / 'output.rch', daily_rows(2, 14))
    mgr = OutputFileManager(tx)
    assert len(mgr.read_rch()) == 28
    write_cio(d, iprint=2)
    with pytest.raises(NotImplementedError):
        mgr.read_rch()


@pytest.mark.parametrize('years', [5, 20])
def test_monthly_returns_only_months(tmp_path, years):
    write_cio(tmp_path, iprint=0, nbyr=years)
    n = 3
    write_rch(tmp_path / 'output.rch', monthly_rows(n, years))
    mgr = OutputFileManager(FakeTxInOut(tmp_path))
    for kwargs in ({}, {'freq': 'MS'}, {'freq': 'M'}):
        df = mgr.read_rch(columns='FLOW_OUTcms', **kwargs)
        assert len(df) == n * 12 * years
        assert df['MON'].between(1, 12).all()
        exp = [y * 100 + m + r / 10 for y in range(years) for m in range(1, 13)
               for r in range(1, n + 1)]
        assert df['FLOW_OUTcms'].tolist() == pytest.approx(exp, rel=1e-4)
        assert df['RCH'].tolist() == [r for _ in range(years * 12) for r in range(1, n + 1)]


def test_monthly_truncated_block_raises(tmp_path):
    write_cio(tmp_path, iprint=0)
    rows = monthly_rows(3, 5)
    write_rch(tmp_path / 'output.rch', rows[:-1])
    with pytest.raises(ValueError, match="Monthly output.rch"):
        OutputFileManager(FakeTxInOut(tmp_path)).read_rch()


def test_monthly_file_with_daily_layout_raises(tmp_path):
    write_cio(tmp_path, iprint=0)
    write_rch(tmp_path / 'output.rch', daily_rows(3, 20))
    with pytest.raises(ValueError):
        OutputFileManager(FakeTxInOut(tmp_path)).read_rch()


def test_yearly_not_implemented(tmp_path):
    write_cio(tmp_path, iprint=2)
    write_rch(tmp_path / 'output.rch', daily_rows(2, 2))
    with pytest.raises(NotImplementedError, match="IPRINT=2"):
        OutputFileManager(FakeTxInOut(tmp_path)).read_rch()


# ---------------------------------------------------------------- parse errors
def test_overflow_field_names_file_line_column(env):
    d, tx = env
    rows = daily_rows(2, 3)
    bad = bytearray(rows[3].encode())
    start, end = ReachMapping.get_colspec('FLOW_OUTcms')
    bad[start:end] = b'*' * (end - start)
    rows[3] = bad.decode()
    path = d / 'output.rch'
    write_rch(path, rows)
    with pytest.raises(ValueError) as ei:
        OutputFileManager(tx).read_rch(columns='FLOW_OUTcms')
    msg = str(ei.value)
    assert 'output.rch' in msg
    assert f"line {RCH_HEADER + 3 + 1}" in msg
    assert "FLOW_OUTcms" in msg and '***' in msg


def test_truncated_line_raises(env):
    d, tx = env
    rows = daily_rows(2, 3)
    rows[2] = rows[2][:50]
    write_rch(d / 'output.rch', rows)
    with pytest.raises(ValueError, match=rf"line {RCH_HEADER + 3}.*truncated"):
        OutputFileManager(tx).read_rch(columns='FLOW_OUTcms')


def test_fortran_missing_e_and_empty_fields(env):
    d, tx = env
    rows = daily_rows(1, 2)
    buf = bytearray(rows[0].encode())
    s, e = ReachMapping.get_colspec('FLOW_OUTcms')
    buf[s:e] = b' 0.2746-139'.rjust(e - s)
    s2, e2 = ReachMapping.get_colspec('SED_OUTtons')
    buf[s2:e2] = b' ' * (e2 - s2)
    rows[0] = buf.decode()
    write_rch(d / 'output.rch', rows)
    df = OutputFileManager(tx).read_rch(columns=['FLOW_OUTcms', 'SED_OUTtons'])
    assert df['FLOW_OUTcms'].iloc[0] == 0.0  # 0.2746E-139 underflows float32
    assert np.isnan(df['SED_OUTtons'].iloc[0])


def test_lf_and_crlf_give_same_data(env):
    d, tx = env
    write_rch(d / 'output.rch', daily_rows(2, 3), eol='\n')
    a = OutputFileManager(tx).read_rch()
    write_rch(d / 'output.rch', daily_rows(2, 3), eol='\r\n')
    b = OutputFileManager(tx).read_rch()
    assert a.equals(b)


# ---------------------------------------------------------------- check_complete
def test_check_complete(env):
    d, tx = env
    path = d / 'output.rch'
    mgr = OutputFileManager(tx)

    with pytest.raises(RuntimeError, match="missing"):
        mgr.check_complete()

    path.write_bytes(b'')
    with pytest.raises(RuntimeError, match="empty"):
        mgr.check_complete()

    write_rch(path, daily_rows(2, 3))
    assert mgr.check_complete() == 6
    assert mgr.check_complete('.rch', expected_rows=6) == 6
    with pytest.raises(RuntimeError, match="expected 7"):
        mgr.check_complete('.rch', expected_rows=7)

    good = path.read_bytes()
    path.write_bytes(good[:-2])  # last line loses its terminator
    with pytest.raises(RuntimeError, match="newline"):
        mgr.check_complete()

    path.write_bytes(good[:-60])  # cut inside the last line, then terminated
    path.write_bytes(good[:-60] + b'\r\n')
    with pytest.raises(RuntimeError, match="unequal length"):
        mgr.check_complete()

    path.write_bytes(good.split(b'\r\n')[0] + b'\r\n')  # header only
    with pytest.raises(RuntimeError):
        mgr.check_complete()


# ---------------------------------------------------------------- sed
def test_sed_mapping_layout():
    m = SedimentMapping.get_mapping()
    assert m['RCH']['colspec'] == (6, 10)
    assert m['MON']['colspec'] == (19, 25)
    assert m['AREAkm2']['colspec'] == (25, 37)
    assert m['TSSmg_L']['colspec'] == (253, 265)
    assert len(m) == 23


def test_read_sed_daily(env):
    d, tx = env
    n = 2
    lines = ['       RCH      GIS   MON']
    for day in (1, 2):
        for r in (1, 2):
            buf = bytearray(b' ' * 265)
            buf[0:5] = b'REACH'
            for info in SedimentMapping.get_mapping().values():
                s, e = info['colspec']
                buf[s:e] = '0.0000E+00'.rjust(e - s).encode()
            buf[6:10] = str(r).rjust(4).encode()
            buf[19:25] = str(day).rjust(6).encode()
            s, e = SedimentMapping.get_colspec('SED_OUTtons')
            buf[s:e] = f"{r * 10 + day:.4E}".rjust(12).encode()
            lines.append(buf.decode())
    (d / 'output.sed').write_text('\r\n'.join(lines) + '\r\n', newline='')
    df = OutputFileManager(tx).read_sed(columns='SED_OUTtons', reach_id=2)
    assert df['MON'].tolist() == [1, 2]
    assert df['SED_OUTtons'].tolist() == pytest.approx([21, 22])


def test_read_sed_monthly_not_implemented(tmp_path):
    write_cio(tmp_path, iprint=0)
    with pytest.raises(NotImplementedError, match="SED_OUTtons"):
        OutputFileManager(FakeTxInOut(tmp_path)).read_sed()
