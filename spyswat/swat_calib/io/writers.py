import math
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from spyswat.swat_calib.io.readers import ReadFileLine, TXT_ENCODING, TXT_NEWLINE
from spyswat.swat_calib.utils.data_info import DATAParameter
from spyswat.logger import Logger


logger = Logger.get_logger(__name__)


class SWATFileFormatError(ValueError):
    """A TxtInOut file does not have the layout a parameter definition expects."""


_METHOD_ALIASES = {
    'replace': 'replace', 'v': 'replace',
    'relative': 'relative', 'r': 'relative',
    'add': 'add', 'a': 'add',
}


def normalize_method(method) -> str:
    """Map a method name or alias to 'replace' | 'relative' | 'add'."""
    key = str(method).strip().lower()
    if key not in _METHOD_ALIASES:
        raise ValueError(
            f"Method '{method}' does not exist, choose: 'replace' ('v'), "
            f"'relative' ('r'), 'add' ('a')."
        )
    return _METHOD_ALIASES[key]


def split_terminator(line: str) -> Tuple[str, str]:
    """Split a line into (body, terminator) where terminator is '', '\\n', '\\r\\n' or '\\r'."""
    body = line.rstrip('\r\n')
    return body, line[len(body):]


def atomic_write_lines(path, lines: List[str], retries: int = 5) -> None:
    """
    Write ``lines`` to ``path`` through a temp file in the same directory and
    ``os.replace``. Text is written as latin-1 without newline translation.
    A read-only target is made writable for the replace and restored afterwards;
    PermissionError on the replace (file briefly locked) is retried.
    """
    path = Path(path)
    try:
        orig_mode = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        orig_mode = None

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    made_writable = False
    try:
        with os.fdopen(fd, 'w', encoding=TXT_ENCODING, newline=TXT_NEWLINE) as f:
            f.writelines(lines)
            f.flush()
            os.fsync(f.fileno())

        if orig_mode is not None:
            os.chmod(tmp_name, orig_mode)
            if not orig_mode & stat.S_IWRITE:
                os.chmod(path, orig_mode | stat.S_IWRITE)
                made_writable = True

        last_err: Optional[Exception] = None
        for attempt in range(max(1, retries)):
            try:
                os.replace(tmp_name, path)
                last_err = None
                break
            except PermissionError as e:
                last_err = e
                time.sleep(0.05 * (attempt + 1))
        if last_err is not None:
            raise last_err
        made_writable = False  # the new file already carries the original mode
    except BaseException:
        if made_writable and orig_mode is not None:
            try:
                os.chmod(path, orig_mode)
            except OSError:
                pass
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class HRUWriter(ReadFileLine):
    SOL_FIELD_WIDTH = 12
    SOL_DATA_START = 27

    def __init__(self, hru_file):
        super().__init__()
        self.hru_file = hru_file
        self.lines = self._read_file(hru_file)
        self._original = list(self.lines)
        self._name = Path(hru_file).name

    def __getitem__(self, i: int) -> str:
        return self.lines[i]

    def __repr__(self):
        return f"HRUWriter(file='{self.hru_file}', lines={len(self.lines)})"

    @property
    def changed(self) -> bool:
        return self.lines != self._original

    # ==================== Public Methods ====================
    def update_param(self, ext_params: List[DATAParameter],
                     new_values: Dict[str, float],
                     method: str = 'replace'):
        """Apply the updates IN MEMORY. Raises SWATFileFormatError (ValueError) on any problem."""
        for param in ext_params:
            value = new_values.get(param.name)
            if value is None:
                logger.warning(f"Not find any '{param.name}'. Continue.")
                continue

            _method = getattr(param, 'method', method)
            self._update(param, value, method=_method)

    def save(self) -> bool:
        """
        Write the file once (temp file + os.replace). Does nothing and returns
        False when nothing changed. The line count and every line length must be
        unchanged.
        """
        if not self.changed:
            logger.debug(f"No change for {self.hru_file}; not written.")
            return False
        assert len(self.lines) == len(self._original), \
            f"{self._name}: line count changed ({len(self._original)} -> {len(self.lines)})"
        for i, (a, b) in enumerate(zip(self._original, self.lines)):
            assert len(a) == len(b), f"{self._name}: length of line {i + 1} changed"
        atomic_write_lines(self.hru_file, self.lines)
        self._original = list(self.lines)
        logger.debug(f"Saved changes to {self.hru_file}")
        return True

    # ==================== Layout helpers ====================
    @classmethod
    def is_sol_layered(cls, param: DATAParameter) -> bool:
        """True for .sol parameters stored as N x 12-wide layer fields after the 27-char label."""
        ext = param.ext if param.ext.startswith('.') else f".{param.ext}"
        return (ext == '.sol' and param.start == cls.SOL_DATA_START
                and param.end - param.start == cls.SOL_FIELD_WIDTH)

    def _error(self, param, line_idx: int, msg: str, text: str = "") -> SWATFileFormatError:
        return SWATFileFormatError(
            f"{self._name}, line {line_idx + 1}, parameter {param.name}{param.ext}: "
            f"{msg}" + (f" | text: {text!r}" if text != "" else "")
        )

    def _body(self, param, line_idx: int) -> Tuple[str, str]:
        if line_idx < 0 or line_idx >= len(self.lines):
            raise self._error(param, line_idx,
                              f"line does not exist (file has {len(self.lines)} lines)")
        return split_terminator(self.lines[line_idx])

    def _sol_fields(self, param, line_idx: int, body: str) -> List[str]:
        """Return the raw 12-char layer fields of a .sol line, validating the alignment."""
        w, s = self.SOL_FIELD_WIDTH, self.SOL_DATA_START
        if len(body) < s + w:
            raise self._error(param, line_idx,
                              f"line shorter than one layer field (length {len(body)})", body)
        data = body[s:]
        if len(data) % w != 0:
            raise self._error(param, line_idx,
                              f"data part after the {s}-char label is {len(data)} chars, "
                              f"not a multiple of {w} (damaged or misaligned .sol line)", body)
        fields = [data[i:i + w] for i in range(0, len(data), w)]
        for k, fld in enumerate(fields):
            try:
                float(fld.strip())
            except ValueError:
                raise self._error(param, line_idx,
                                  f"layer {k + 1} field is not a number", fld) from None
            if fld[-1] == ' ':
                raise self._error(param, line_idx,
                                  f"layer {k + 1} field is not right-aligned in its "
                                  f"{w}-char slot", fld)
        return fields

    # ==================== Dispatch ====================
    def _update(
        self,
        param: DATAParameter,
        new_value: float,
        method: str = 'replace',
    ):
        method = normalize_method(method)
        if self.is_sol_layered(param):
            layer = getattr(param, 'layer', None)
            self.__update_sol(param, new_value, method, layer)
        else:
            self.__update_hru(param, new_value, method=method)

    # ==================== Core Update Methods ====================

    def _require_finite(self, param, line_idx: int, value: float) -> None:
        if not math.isfinite(value):
            raise self._error(param, line_idx, f"new value {value!r} is not finite")

    def _format(self, param, line_idx: int, value: float, width: int) -> str:
        self._require_finite(param, line_idx, value)
        text = f"{value:.{param.round}f}"
        if len(text) > width:
            raise self._error(param, line_idx,
                              f"new value {text!r} is wider than the {width}-char field")
        return text.rjust(width)

    def __update_sol(self, param, new_value, method='replace', layer=None):
        idx = param.line
        body, term = self._body(param, idx)
        fields = self._sol_fields(param, idx, body)
        n_layers = len(fields)

        if layer is None:
            layers_to_update = range(n_layers)
        else:
            if layer < 0 or layer >= n_layers:
                raise self._error(param, idx,
                                  f"layer {layer} requested but the line has {n_layers} layers",
                                  body)
            layers_to_update = [layer]

        w, s = self.SOL_FIELD_WIDTH, self.SOL_DATA_START
        new_fields = list(fields)
        for lyr in layers_to_update:
            old_value = float(fields[lyr].strip())
            value = self._method(method, old_value, new_value)
            self._require_finite(param, idx, value)
            value = self._min_max_check(param, value)
            new_fields[lyr] = self._format(param, idx, value, w)
        self.lines[idx] = body[:s] + "".join(new_fields) + term

    def __update_hru(
        self,
        param: DATAParameter,
        new_value: float,
        method: str = 'replace'
    ):
        idx = param.line
        body, term = self._body(param, idx)
        if len(body) < param.end:
            raise self._error(param, idx,
                              f"line is {len(body)} chars, shorter than the field end "
                              f"{param.end}", body)

        old_value = None
        if method != 'replace':
            raw = body[param.start:param.end]
            try:
                old_value = float(raw.strip())
            except ValueError:
                raise self._error(param, idx,
                                  f"old value cannot be parsed (method '{method}' needs it)",
                                  raw) from None
        value = self._method(method, old_value, new_value)
        self._require_finite(param, idx, value)
        value = self._min_max_check(param, value)

        value_str = self._format(param, idx, value, param.end - param.start)
        self.lines[idx] = body[:param.start] + value_str + body[param.end:] + term

    # ==================== Calculation Helpers ====================

    def _method(self, method: str, old_value: Optional[float], value: float) -> float:
        method = normalize_method(method)
        if method == 'replace':
            return value
        if method == 'relative':
            return old_value * (1 + value)
        return old_value + value

    def _min_max_check(self, param: DATAParameter, new_value: float) -> float:
        clamped = max(param.vmin, min(new_value, param.vmax))
        if clamped != new_value:
            logger.debug(
                f"{self._name}: {param.name}{param.ext} value {new_value} clamped "
                f"to {clamped} (range [{param.vmin}, {param.vmax}])"
            )
        return clamped

    # ==================== Read-only inspection ====================

    def inspect_param(self, param: DATAParameter) -> List[Tuple[int, str, str]]:
        """
        Check the layout of one parameter without modifying anything.
        Returns a list of (line_1based, problem, text).
        """
        out: List[Tuple[int, str, str]] = []
        idx = param.line
        if idx < 0 or idx >= len(self.lines):
            return [(idx + 1, 'line missing', '')]
        body, _ = split_terminator(self.lines[idx])

        def check_range(v: float, text: str):
            if not (param.vmin <= v <= param.vmax):
                out.append((idx + 1, f'value {v} out of range [{param.vmin}, {param.vmax}]', text))

        if self.is_sol_layered(param):
            w, s = self.SOL_FIELD_WIDTH, self.SOL_DATA_START
            if len(body) < s + w:
                return [(idx + 1, 'line too short', body)]
            data = body[s:]
            if len(data) % w != 0:
                out.append((idx + 1, f'sol misalignment: data part {len(data)} chars, '
                                     f'not a multiple of {w}', body))
            for k in range(0, len(data) - len(data) % w, w):
                fld = data[k:k + w]
                try:
                    v = float(fld.strip())
                except ValueError:
                    out.append((idx + 1, f'slice not numeric (layer {k // w + 1})', fld))
                    continue
                if fld[-1] == ' ':
                    out.append((idx + 1, f'sol misalignment: layer {k // w + 1} '
                                         f'not right-aligned', fld))
                check_range(v, fld)
            return out

        if len(body) < param.end:
            return [(idx + 1, 'line too short', body)]
        raw = body[param.start:param.end]
        try:
            v = float(raw.strip())
        except ValueError:
            out.append((idx + 1, 'slice not numeric', raw))
        else:
            check_range(v, raw)
        # ':' is the legitimate label delimiter of some .sol header lines
        if param.start > 0 and body[param.start - 1] not in ' \t:':
            out.append((idx + 1, 'non-blank character before field', body[param.start - 1:param.end]))
        if param.end < len(body) and body[param.end] not in ' \t':
            out.append((idx + 1, 'non-blank character after field', body[param.start:param.end + 1]))
        return out
