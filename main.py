import pandas as pd
from matplotlib import pyplot as plt

from swat_toolkit import SWATProject

txinout_path = r'D:\Project\2025_IVCEES\SWAT_Ba_Basin\SWAT_Ba_Basin\SWAT_Ba_Basin\SWAT\Bariverbasin\Scenarios\Default\TxtInOut'
swat_exe_path = r"D:\RSWAT\_SWAT_RUN\swat_695.exe"
swat_param_path = r"D:\RSWAT\swatParam.txt"

cungson_obs = pd.read_csv(r"D:\DATA_STORAGE\_data\.dataall\Q_BA_0003\flow_date_flow2019\Q_BA_0003.csv",
                          index_col='date', parse_dates=['date'])


project = SWATProject(txinout_path, swat_exe_path, swat_param_path)

rch = project._output_manager.read_rch(['RCH',"MON",'FLOW_OUTcms'])
cungson = rch.loc[(rch['RCH'] == 8) & (rch['MON'] <= 366)]

date = pd.date_range(project.get_date_start(), periods=len(cungson))
cungson.set_index(date, inplace=True)
# print(year)
# project.statistic(cungson['FLOW_OUTcms'],cungson_obs['discharge'])
# print(cungson)
fig, ax = plt.subplots()

ax.plot(cungson.index, cungson['FLOW_OUTcms'], color='red', label='Flow Outcms', alpha=0.5)
ax.plot(cungson_obs.index, cungson_obs['discharge'], alpha=0.5, label='Discharge')

plt.show()



