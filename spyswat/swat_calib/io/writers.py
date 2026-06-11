from typing import Dict, List, Optional

from spyswat.swat_calib.io.readers import ReadFileLine
from spyswat.swat_calib.utils.data_info import DATAParameter
from spyswat.logger import Logger


logger = Logger.get_logger(__name__)


class HRUWriter(ReadFileLine):
    SOL_FIELD_WIDTH = 12
    SOL_DATA_START = 27

    def __init__(self, hru_file):
        super().__init__()
        self.hru_file = hru_file
        self.lines = self._read_file(hru_file)

    def __getitem__(self, i: int) -> str:
        return self.lines[i]

    def __repr__(self):
        return f"HRUWriter(file='{self.hru_file}', lines={len(self.lines)})"

    # ==================== Public Methods ====================
    def update_param(self, ext_params: List[DATAParameter],
                     new_values: Dict[str, float],
                     method: str = 'replace'):

        for param in ext_params:
            value = new_values.get(param.name)
            if value is None:
                logger.warning(f"Not find any '{param.name}'. Continue.")
                continue

            _method = getattr(param, 'method', method)
            self._update(param, value, method=_method)

    def save(self):
        with open(self.hru_file, "w", encoding='utf-8') as f:
            f.writelines(self.lines)
        logger.debug(f"Saved changes to {self.hru_file}")

    # ==================== Dispatch ====================
    def _update(
        self,
        param: DATAParameter,
        new_value: float,
        method: str = 'replace',
    ):
        if param.ext == '.sol' or param.ext == 'sol':
            layer = getattr(param, 'layer', None)
            self.__update_sol(param, new_value, method, layer)
        else:
            self.__update_hru(param, new_value, method=method)

    # ==================== Core Update Methods ====================

    def __update_sol(self, param, new_value, method='replace', layer=None):
        line = self.lines[param.line]
        n_layers = self.__count_layers(line)

        layers_to_update = range(n_layers) if layer is None else [layer]

        for lyr in layers_to_update:
            if lyr >= n_layers:
                logger.warning(f"Layer {lyr} >= n_layers {n_layers}. Skipping.")
                continue
            line = self.lines[param.line]
            old_value = self._get_value_sol_layer(line, lyr)
            value = self._method(method, old_value, new_value)
            value = self._min_max_check(param, value)

            col_start = self.SOL_DATA_START + lyr * self.SOL_FIELD_WIDTH
            col_end = col_start + self.SOL_FIELD_WIDTH

            value_str = f"{value:.{param.round}f}".rjust(self.SOL_FIELD_WIDTH)
            self.lines[param.line] = line[:col_start] + value_str + line[col_end:]


    def __update_hru(
        self,
        param: DATAParameter,
        new_value: float,
        method: str = 'replace'
    ):
        line = self.lines[param.line]

        old_value = self._get_value_positional(line, param.start, param.end)
        value = self._method(method, old_value, new_value)
        value = self._min_max_check(param, value)

        field_width = param.end - param.start
        value_str = f"{value:.{param.round}f}".rjust(field_width)
        self.lines[param.line] = line[:param.start] + value_str + line[param.end:]

    # ==================== Calculation Helpers ====================

    def _method(self, method: str, old_value: float, value: float) -> float:
        if method == 'replace' or method == 'v':
            return value
        elif method == 'relative' or method == 'r':
            return old_value * (1 + value)
        elif method == 'add':
            return old_value + value
        else:
            raise ValueError(f"Method '{method}' not exits, choose: 'replace', 'relative', 'add'.")

    def _min_max_check(self, param: DATAParameter, new_value: float) -> float:
        return max(param.vmin, min(new_value, param.vmax))

    # ==================== Value Parsers ====================

    def _get_value_positional(self, line: str, start: int, end: int) -> float:
        try:
            return float(line[start:end].strip())
        except ValueError:
            logger.warning(
                f"Không thể parse giá trị tại [{start}:{end}] "
                f"trong dòng: {line!r}. Trả về 0.0."
            )
            return 0.0

    def _get_value_sol_layer(self, line: str, layer: int) -> float:
        try:
            col_start = self.SOL_DATA_START + layer * self.SOL_FIELD_WIDTH
            col_end = col_start + self.SOL_FIELD_WIDTH
            return float(line[col_start:col_end].strip())
        except (ValueError, IndexError) as e:
            logger.warning(f"Không thể parse SOL layer {layer}: {e}. Trả về 0.0.")
            return 0.0

    def __count_layers(self, line: str) -> int:
        try:
            data_part = line[self.SOL_DATA_START:].rstrip('\n').rstrip()
            n = len(data_part) // self.SOL_FIELD_WIDTH
            return max(n, 0)
        except Exception:
            logger.warning(f"Không đếm được layer trong dòng: {line!r}")
            return 0