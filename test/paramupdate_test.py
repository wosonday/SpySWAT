from swat_calib.io import SWATParam
from swat_calib.core import TxInOut
from swat_calib.io import HRURead
import pandas as pd


swat = r'D:\Project\2025_IVCEES\SWAT_Ba_Basin\SWAT_Ba_Basin\SWAT_Ba_Basin\SWAT\Bariverbasin\Scenarios\Default\TxtInOut'

param = r'D:\RSWAT\swatParam.txt'
swat_param = SWATParam(param)
txinout = TxInOut(swat)
hrus = txinout.get_hru_file('.sol')


param11 = ['CN2']


par = swat_param.get_params(param11)
df = pd.DataFrame()
records = []
for ext, param_dict in par.items():
    if ext == '.bsn':
        hrus = txinout.get_watershed_file(ext)
    else:
        hrus = txinout.get_hru_file(ext)
    for hru in hrus:
        reader = HRURead(hru)
        row = {"hru": hru.stem}
        for pname in param_dict:
            p = swat_param.get(pname)
            val = reader.get_value(p)
            row[pname] = float(val)
        records.append(row)
df = pd.DataFrame(records)
df_merged = df.sort_values(by="hru").groupby("hru").first().reset_index()
# df_merged.to_csv('sBa.csv', index=False)
print(df_merged)
