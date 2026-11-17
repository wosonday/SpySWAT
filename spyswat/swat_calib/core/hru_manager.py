from collections import defaultdict
from pathlib import Path

from spyswat.swat_calib.io.parameters import SWATParam
from spyswat.swat_calib.core.txinout import TxInOut
from spyswat.swat_calib.io.readers import HRURead
from spyswat.swat_calib.io.writers import HRUWriter, atomic_write_lines
from spyswat.logger import Logger
import pandas as pd

logger = Logger.get_logger(__name__)


class HRUManager:
    def __init__(self, txinout: TxInOut, swat_param: SWATParam):
        self.txinout = txinout
        self.swat_param = swat_param

    def read_multi_hru_param_values(self, param: list, hru_name: bool = True,
                                    subbasin=None, attrs=None) -> pd.DataFrame:
        """
        Read HRU parameter values from TxtInOut.

        Each param is located by the file/line/column position in swatParam.txt
        (same DATAParameter coordinates used by HRUWriter), so read and write stay
        symmetric.

        Args:
            param:    list of 'name.ext' keys, e.g. ['CN2.mgt', 'ALPHA_BF.gw'].
            hru_name: True -> prepend the 'hru' column (file stem); False -> params only.
            subbasin: optional subbasin filter (int or list of int); None = all.
            attrs:    optional HRU header attributes to join, e.g.
                      ['Subbasin', 'Luse', 'Soil', 'Slope'].
        """
        param_by_ext = self.swat_param.get_params(param)
        data = defaultdict(dict)

        for ext, names in param_by_ext.items():
            for hru_file in self._resolve_files(ext, subbasin):
                reader = HRURead(hru_file)
                for name in names:
                    p = self.swat_param.get(name)
                    data[hru_file.stem][name] = self._safe_float(reader.get_value(p))

        df = (pd.DataFrame.from_dict(data, orient='index')
                .reindex(columns=param)
                .sort_index())

        if attrs:
            info = pd.DataFrame(self.txinout.hru_info).set_index('name')
            keep = [a for a in attrs if a in info.columns]
            df = df.join(info[keep])
            df = df[keep + [c for c in df.columns if c not in keep]]

        if hru_name:
            df.insert(0, 'hru', df.index)
        return df.reset_index(drop=True)

    def _resolve_files(self, ext: str, subbasin_filter=None):
        """Resolve the TxtInOut files that hold parameters of a given extension."""
        ext = ext if ext.startswith('.') else f".{ext}"
        if ext == '.bsn':
            return [self.txinout.get_watershed_file(ext)]
        if subbasin_filter is None:
            return self.txinout.get_hru_file(ext)
        subs = subbasin_filter if isinstance(subbasin_filter, list) else [subbasin_filter]
        return [f for s in subs for f in self.txinout.get_hru_file(ext, s)]

    @staticmethod
    def _safe_float(raw):
        try:
            return float(str(raw).strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _validate_param_keys(param: dict):
        """
        Ensure all keys use 'name.ext' format (e.g. 'CN2.mgt', 'ESCO.hru').
        Raises ValueError listing the offending keys if any bare names found.
        """
        bad = [k for k in param if '.' not in k]
        if bad:
            raise ValueError(
                f"Parameter key(s) {bad} missing file extension. "
                f"Use 'name.ext' format, e.g. 'CN2.mgt', 'ALPHA_BF.gw', 'ESCO.hru'."
            )

    def update_params(self, param: dict, subbasin=None):
        """
        Apply all parameter updates. Every file is read once, all updates and
        passes for it are applied in order in memory and validated, and only then
        is each changed file written once. A ValueError is raised before any file
        is written when one update is invalid.
        """
        self._validate_param_keys(param)
        all_updates = []
        for param_name, groups in param.items():
            if isinstance(groups, tuple):
                groups = [groups]

            for pass_idx, group in enumerate(groups):
                if len(group) < 2:
                    logger.warning(
                        f"[Pass {pass_idx + 1}] Param '{param_name}' missing value/method. Skipping."
                    )
                    continue

                value, method = group[0], group[1]
                raw_sub = group[2] if len(group) > 2 else subbasin
                subbasin_filter = None if (raw_sub is None or raw_sub == "All") else raw_sub

                logger.debug(
                    f"[Pass {pass_idx + 1}] Param: {param_name} | Method: {method} "
                    f"| Value: {value} | Sub: {subbasin_filter or 'All'}"
                )

                all_updates.extend(
                    self._collect_file_updates(param_name, value, method, subbasin_filter)
                )
        self._apply_updates(all_updates)

    def update_by_df(self, df: pd.DataFrame, param_name='param', method='method',
                     value='value', sub='subbasin'):
        all_updates = []
        for row in df.itertuples(index=False):
            p_raw = getattr(row, param_name, None)
            if pd.isna(p_raw):
                continue

            pname = str(p_raw)
            if '.' not in pname:
                raise ValueError(
                    f"Param '{pname}' in DataFrame missing file extension. "
                    f"Use 'name.ext' format, e.g. 'CN2.mgt'."
                )

            val = getattr(row, value)
            mth = getattr(row, method)

            raw_sub = getattr(row, sub, None) if sub in df.columns else None
            if raw_sub is None or pd.isna(raw_sub) or raw_sub == "All":
                subbasin_filter = None
            else:
                subbasin_filter = [int(s.strip()) for s in str(raw_sub).split(',')]

            logger.info(
                f"Updating | Param: {pname} | Method: {mth} | Value: {val} | Sub: {subbasin_filter}"
            )

            all_updates.extend(self._collect_file_updates(pname, val, mth, subbasin_filter))
        self._apply_updates(all_updates)

    def _collect_file_updates(self, pname: str, val: float, mth: str, subbasin_filter) -> list:
        par_info = self.swat_param.get(pname)
        if par_info is None:
            logger.warning(f"Param '{pname}' not found. Skipping.")
            return []

        hru_files = self._resolve_files(par_info.ext, subbasin_filter)

        if not hru_files:
            logger.warning(f"No files found for param '{pname}'. Skipping.")
            return []

        return [(hru_file, par_info, val, mth) for hru_file in hru_files]

    def _apply_updates(self, file_updates: list):
        """
        file_updates: ordered list of (file, DATAParameter, value, method).
        Phase 1 reads each file once and applies every update in memory (raises
        before anything is written); phase 2 writes each changed file once.
        """
        writers: dict = {}
        for hru_file, par_info, val, mth in file_updates:
            key = str(hru_file)
            writer = writers.get(key)
            if writer is None:
                writer = writers[key] = HRUWriter(hru_file)
            writer.update_param([par_info], {par_info.name: val}, method=mth)

        written = []
        try:
            for writer in writers.values():
                original = list(writer._original)
                if writer.save():
                    written.append((writer.hru_file, original))
        except BaseException:
            # Best effort: put back the files already written in this call.
            for path, original in written:
                try:
                    atomic_write_lines(path, original)
                except Exception:
                    logger.error(f"Could not restore {path} after a failed update.")
            raise

    def validate_inputs(self, params=None) -> pd.DataFrame:
        """
        Check, without modifying anything, that every (parameter, file) location
        matches the layout in the parameter file.

        Args:
            params: list of 'name.ext' keys; default all keys of the parameter file.

        Returns:
            DataFrame with columns file, param, line (1-based), problem, text.
            Empty when everything is fine.
        """
        keys = list(params) if params is not None else self.swat_param.available_keys()
        rows = []
        cache: dict = {}
        for key in keys:
            par = self.swat_param.params.get(key)
            if par is None or not par.ext:
                rows.append({'file': '', 'param': key, 'line': 0,
                             'problem': 'parameter has no file extension or is unknown',
                             'text': ''})
                continue
            for f in self._resolve_files(par.ext, None) or []:
                fname = Path(f).name
                try:
                    if str(f) not in cache:
                        cache[str(f)] = HRUWriter(f)
                    problems = cache[str(f)].inspect_param(par)
                except OSError as e:
                    problems = [(0, 'file unreadable', str(e))]
                for line, problem, text in problems:
                    rows.append({'file': fname, 'param': key, 'line': line,
                                 'problem': problem, 'text': text})
        return pd.DataFrame(rows, columns=['file', 'param', 'line', 'problem', 'text'])
