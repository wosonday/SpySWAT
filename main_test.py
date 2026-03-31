import pandas as pd
import numpy as np
from matplotlib import pyplot as plt

from swat_toolkit import SWATProject

txinout_path = r'D:\Project\2025_IVCEES\SWAT_Ba_Basin\SWAT_Ba_Basin\SWAT\Bariverbasin\Scenarios\Default\TxtInOut'
swat_exe_path = r"D:\RSWAT\_SWAT_RUN\swat_695.exe"
swat_param_path = r"D:\RSWAT\swatParam.txt"

cungson_obs = pd.read_csv(r"D:\DATA_STORAGE\_data\.dataall\Q_BA_0003\flow_date_flow2019\Q_BA_0003.csv",
                          index_col='date', parse_dates=['date'])
cungson_obs = cungson_obs.loc['1983-01-01': '2019-12-31']
ankhe_obs = pd.read_csv(r"D:\DATA_STORAGE\_data\.dataall\Q_BA_0001\flow_date_flow2019\Q_BA_0001.csv",
                          index_col='date', parse_dates=['date'])
ankhe_obs = ankhe_obs.loc['1983-01-01': '2019-12-31']

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

rch = project.output_manager.read_rch('FLOW_OUTcms', reach_id=[8, 51])

cungson = rch
n_rch = cungson['RCH'].nunique()
dates = project.get_date_range()
dates_repeated = np.repeat(dates, n_rch)
cungson['date'] = dates_repeated
pivot_df = cungson.pivot(index='date', columns='RCH', values='FLOW_OUTcms')
pivot_df = pivot_df.loc['1983-01-01': '2019-12-31']


print(project.statistic.calculate_statistics(pivot_df[8], cungson_obs['discharge']))
print(project.statistic.calculate_statistics(pivot_df[51], ankhe_obs['discharge']))
print(pivot_df)

fig, ax = plt.subplots()

ax.plot(pivot_df.index, pivot_df[51], color='red', label='Simulated', alpha=0.6)
ax.plot(ankhe_obs.index, ankhe_obs['discharge'], alpha=0.6, label='Observed')

fig.legend()
ax.grid()
fig.suptitle("An Khe Station")
plt.show()



