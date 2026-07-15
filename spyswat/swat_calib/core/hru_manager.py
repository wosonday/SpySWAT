from collections import defaultdict

from spyswat.swat_calib.io.parameters import SWATParam
from spyswat.swat_calib.core.txinout import TxInOut
from spyswat.swat_calib.io.readers import HRURead
from spyswat.swat_calib.io.writers import HRUWriter
from spyswat.logger import Logger
import pandas as pd

logger = Logger.get_logger(__name__)


class HRUManager:
    def __init__(self, txinout: TxInOut, swat_param: SWATParam):
        self.txinout = txinout
        self.swat_param = swat_param

    def read_multi_hru_param_values(self, param: list, hru_name: bool = True,
                                    subbasin=None) -> pd.DataFrame:
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
        self._validate_param_keys(param)
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

                updates = self._collect_file_updates(param_name, value, method, subbasin_filter)
                self._apply_updates(updates)

    def update_by_df(self, df: pd.DataFrame, param_name='param', method='method',
                     value='value', sub='subbasin'):
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

            updates = self._collect_file_updates(pname, val, mth, subbasin_filter)
            self._apply_updates(updates)

    def _collect_file_updates(self, pname: str, val: float, mth: str, subbasin_filter) -> dict:
        par_info = self.swat_param.get(pname)
        if par_info is None:
            logger.warning(f"Param '{pname}' not found. Skipping.")
            return {}

        hru_files = self._resolve_files(par_info.ext, subbasin_filter)

        if not hru_files:
            logger.warning(f"No files found for param '{pname}'. Skipping.")
            return {}

        return {hru_file: (par_info, val, mth) for hru_file in hru_files}

    def _apply_updates(self, file_updates: dict):
        for hru_file, (par_info, val, mth) in file_updates.items():
            writer = HRUWriter(hru_file)
            writer.update_param([par_info], {par_info.name: val}, method=mth)
            writer.save()
