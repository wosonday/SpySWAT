from collections import defaultdict

from spyswat.swat_calib.io.parameters import SWATParam
from spyswat.swat_calib.core.txinout import TxInOut
from spyswat.swat_calib.io.readers import HRURead
from spyswat.swat_calib.io.writers import HRUWriter
from spyswat.logger import Logger
import pandas as pd

Logger.init(log_dir="logs", log_file="run.log", level="WARNING")
logger = Logger.get_logger(__name__)

class HRUManager:
    def __init__(self, txinout: TxInOut, swat_param: SWATParam):
        self.txinout = txinout
        self.swat_param = swat_param

    def read_muti_hru_param_values(self, param: list):
        param_ = self.swat_param.get_params(param)
        records = []
        for ext, param_dict in param_.items():
            if ext == '.bsn':
                hrs = [self.txinout.get_watershed_file(ext)]
            else:
                hrs = self.txinout.get_hru_file(ext)
            for hru in hrs:
                reader = HRURead(hru)
                row = {"hru": hru.stem}
                for name in param_dict:
                    p = self.swat_param.get(name)
                    val = reader.get_value(p)
                    row[name] = float(val)
                records.append(row)
        df = pd.DataFrame(records)
        df_merged = df.sort_values(by="hru").groupby("hru").first().reset_index()
        return df_merged

    def update_params(self, param: dict, subbasin=None):
        for param_name, groups in param.items():
            if isinstance(groups, tuple):
                groups = [groups]

            for pass_idx, group in enumerate(groups):
                if len(group) < 2:
                    logger.warning(f"[Pass {pass_idx + 1}] Param '{param_name}' thiếu value/method. Skipping.")
                    continue

                value, method = group[0], group[1]
                raw_sub = group[2] if len(group) > 2 else subbasin
                subbasin_filter = None if (raw_sub is None or raw_sub == "All") else raw_sub

                logger.info(
                    f"[Pass {pass_idx + 1}] Param: {param_name} | Method: {method} | Value: {value} | Sub: {subbasin_filter or 'All'}")

                updates = self._collect_file_updates(param_name, value, method, subbasin_filter)
                self._apply_updates(updates)

    def update_by_df(self, df: pd.DataFrame, param_name='param', method='method', value='value', sub='subbasin'):
        for row in df.itertuples(index=False):
            p_raw = getattr(row, param_name, None)
            if pd.isna(p_raw):
                continue

            pname, val, mth = str(p_raw), getattr(row, value), getattr(row, method)

            raw_sub = getattr(row, sub, None) if sub in df.columns else None
            if raw_sub is None or pd.isna(raw_sub) or raw_sub == "All":
                subbasin_filter = None
            else:
                subbasin_filter = [int(s.strip()) for s in str(raw_sub).split(',')]

            logger.info(f"Updating | Param: {pname} | Method: {mth} | Value: {val} | Sub: {subbasin_filter}")

            updates = self._collect_file_updates(pname, val, mth, subbasin_filter)
            self._apply_updates(updates)

    def _build_param_dict(self, pname: str, val: float, mth: str) -> dict:
        try:
            par_info = self.swat_param.get(pname)
        except KeyError as e:
            logger.warning(str(e))
            return {}
        ext = par_info.ext.lstrip('.')
        return {ext: {pname: (val, mth)}}

    def _collect_file_updates(self, pname: str, val: float, mth: str, subbasin_filter) -> dict:
        par_info = self.swat_param.get(pname)
        if par_info is None:
            logger.warning(f"Param '{pname}' not found. Skipping.")
            return {}

        ext = par_info.ext if par_info.ext.startswith('.') else f".{par_info.ext}"

        if ext == '.bsn':
            hru_files = [self.txinout.get_watershed_file(ext)]
        elif subbasin_filter is None:
            hru_files = self.txinout.get_hru_file(ext)
        else:
            sub_list = subbasin_filter if isinstance(subbasin_filter, list) else [subbasin_filter]
            hru_files = [f for s in sub_list for f in self.txinout.get_hru_file(ext, s)]

        if not hru_files:
            logger.warning(f"No files found for ext '{ext}'. Skipping.")
            return {}

        return {hru_file: (par_info, val, mth) for hru_file in hru_files}

    def _apply_updates(self, file_updates: dict):
        for hru_file, (par_info, val, mth) in file_updates.items():
            writer = HRUWriter(hru_file)
            writer.update_param([par_info], {par_info.name: val}, method=mth)
            writer.save()