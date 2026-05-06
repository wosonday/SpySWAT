import pandas as pd
from matplotlib import pyplot as plt

from spyswat import SWATProject

txinout_path = r'D:\Project\2025_IVCEES\SWAT_Ba_Basin\SWAT_Ba_Basin\SWAT_Ba_Basin\SWAT\Bariverbasin\Scenarios\Default\TxtInOut'
swat_exe_path = r"D:\RSWAT\_SWAT_RUN\swat_695.exe"
swat_param_path = r"D:\RSWAT\swatParam.txt"
user_param = 'src/user19Params.csv'

cungson_obs = pd.read_csv(r"D:\DATA_STORAGE\_data\.dataall\Q_BA_0003\flow_date_flow2019\Q_BA_0003.csv",
                          index_col='date', parse_dates=['date'])
ankhe_obs = pd.read_csv(r"D:\DATA_STORAGE\_data\.dataall\Q_BA_0001\flow_date_flow2019\Q_BA_0001.csv",
                          index_col='date', parse_dates=['date'])

cungson_obs = cungson_obs.loc['1983-01-01':]
ankhe_obs = ankhe_obs.loc['1983-01-01':]

project = SWATProject(txinout_path, swat_exe_path, swat_param_path)

output = project.output_manager.read_rch(['RCH','MON','FLOW_OUTcms'])

date_rangee = project.get_date_range()
sim_cungson = output.loc[(output['RCH'] == 8) & (output['MON'] <= 366)].copy().set_index(date_rangee)
sim_ankhe = output.loc[(output['RCH'] == 8) & (output['MON'] <= 366)].copy().set_index(date_rangee)

fig, ax = plt.subplots()

ax.plot(sim_cungson.index, sim_cungson['FLOW_OUTcms'], color='red', label='Simulated', alpha=0.6)
ax.plot(cungson_obs.index, cungson_obs['discharge'], alpha=0.6, label='Observed')

fig.legend()
fig.suptitle('Cung Son')
ax.grid()
plt.show()

fig2, ax2 = plt.subplots()
ax2.plot(sim_ankhe.index, sim_ankhe['FLOW_OUTcms'], color='red', label='Simulated', alpha=0.6)
ax2.plot(ankhe_obs.index, ankhe_obs['discharge'], alpha=0.6, label='Observed')

fig2.legend()
fig2.suptitle('An Khe')
ax2.grid()
plt.show()
