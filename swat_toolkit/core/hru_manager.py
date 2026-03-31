from swat_toolkit.io.parameters import SWATParam
from swat_toolkit.core.txinout import TxInOut
from swat_toolkit.io.readers import HRURead
from swat_toolkit.io.writers import HRUWriter
import pandas as pd


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
                for pname in param_dict:
                    p = self.swat_param.get(pname)
                    val = reader.get_value(p)
                    row[pname] = float(val)
                records.append(row)
        df = pd.DataFrame(records)
        df_merged = df.sort_values(by="hru").groupby("hru").first().reset_index()
        return df_merged

    def update_params(self, param, subbasin = None):
        for param_name, values in param.items():
            value = values[0]
            method = values[1]
            subbasin_filter = values[2] if len(values) > 2 else None
            param_dict = self.swat_param.get_param_by_name({param_name: (value, method)})

            for ext, ext_params in param_dict.items():
                if subbasin_filter is None:
                    hru_files = self.txinout.get_hru_file(ext)
                else:
                    hru_files = []
                    for sub in subbasin_filter:
                        hru_files += self.txinout.get_hru_file(ext, sub)

                for hru_file in hru_files:
                    writer = HRUWriter(hru_file)
                    ext_param_list = []
                    new_values = {}
                    for pname, (val, mth) in ext_params.items():
                        par_info = self.swat_param.get(pname)
                        par_info.method = mth
                        ext_param_list.append(par_info)
                        new_values[pname] = val
                    writer.update_param(ext_param_list, new_values)
                    print('='* 20)
                    print(f"{hru_file} [sub={subbasin_filter}]: updated")
                    print(f"           {param_name} = {value}, [method={method}]\n")
                    writer.save()


    def read_hru_param_values(self, param: str):
        pass