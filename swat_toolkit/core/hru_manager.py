from swat_toolkit.io.parameters import SWATParam
from swat_toolkit.core.txinout import TxInOut
from swat_toolkit.io.readers import HRURead
import pandas as pd

class HRUManager:
    def __init__(self, txinout: TxInOut, swat_param: SWATParam):
        self.txinout = txinout
        self.swat_param = swat_param

    def read_param_values(self, param: list):
        param_ = self.swat_param.get_params(param)
        records = []
        for ext, param_dict in param_.items():
            if ext == '.bsn':
                hrs = self.txinout.get_watershed_file(ext)
            else:
                hrs = self.txinout.get_hru_file(ext)
            for hru in hrs:
                reader = HRURead(hru)
                row = {"hru": hru.stem}
                for pname in param_dict:
                    p = self.swat_param.get(pname)
                    val = reader.get_value(p)
                    row[pname] = float(val)
                records.append(row)
        df = pd.DataFrame(records)
        df_merged = df.sort_values(by="hru").groupby("hru").first().reset_index()
        return df_merged