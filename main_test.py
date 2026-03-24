import pandas as pd
from matplotlib import pyplot as plt

from swat_toolkit import SWATProject

txinout_path = r'D:\Project\2025_IVCEES\SWAT_Ba_Basin\SWAT_Ba_Basin\TxtInOut'
swat_exe_path = r"D:\RSWAT\_SWAT_RUN\swat_695.exe"
swat_param_path = r"D:\RSWAT\swatParam.txt"

cungson_obs = pd.read_csv(r"D:\DATA_STORAGE\_data\.dataall\Q_BA_0003\flow_date_flow2019\Q_BA_0003.csv",
                          index_col='date', parse_dates=['date'])

parametter = {
    "CN2"       : (-0.249, 'relative'),
    "ALPHA_BF"  : (0.506, 'replace'),
    "GW_DELAY"  : (436.905, 'replace'),
    "GWQMN"     : (3744.065, 'replace'),
    "RCHRG_DP"  : (0.462, 'relative'),
    "GW_REVAP"  : (1.989, 'relative'),
    "LAT_TTIME" : (134.069, 'relative'),
    "OV_N"      : (0.091, 'relative'),
    "ESCO"      : (0.366, 'relative'),
    "SLSUBBSN"  : (0.107, 'relative'),
    "HRU_SLP"   : (0.203, 'relative'),
    "SOL_AWC"   : (0.32, 'relative'),
    "SOL_K"     : (0.243, 'relative'),
    "SOL_BD"    : (0.138, 'relative'),
    "CH_N2"     : (0.072, 'relative'),
    "CH_K2"     : (407.968, 'relative'),
    "ALPHA_BNK" : (0.112, 'relative'),
    "SURLAG"    : (9.645, 'relative'),
    "EPCO"      : (0.677, 'relative')
}



project = SWATProject(txinout_path, swat_exe_path, swat_param_path)

project.hru_manager.update_params(parametter)

rch = project._output_manager.read_rch(['RCH',"MON",'FLOW_OUTcms'])
cungson = rch.loc[(rch['RCH'] == 8) & (rch['MON'] <= 366)]

cungson.set_index(project.get_date_range(), inplace=True)

fig, ax = plt.subplots()

ax.plot(cungson.index, cungson['FLOW_OUTcms'], color='red', label='Simulated', alpha=0.5)
ax.plot(cungson_obs.index, cungson_obs['discharge'], alpha=0.5, label='Observed')

fig.legend()
plt.show()

