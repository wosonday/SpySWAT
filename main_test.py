import pandas as pd
import numpy as np
from pathlib import Path

from swat_toolkit import SWATProject

years = ['LUC1992', 'LUC2000', 'LUC2010', 'LUC2020']

swat_exe_path = r"D:\RSWAT\_SWAT_RUN\swat_637_101.exe"
swat_param_path = r"D:\RSWAT\swatParam.txt"

# for year in years:
#     if year == 'LUC1992':
#         txinout_path = r'D:\Project\2026_Nafosted-VLU\SWAT\MATHY_RUN\LUC1992\CPC_SWAT_First\CPC_TxtInOut\TxtInOut'
#     else:
#         txinout_path = fr'D:\Project\2026_Nafosted-VLU\SWAT\{year}\SWAT\Scenarios\Default\TxtInOut'
#
#     working_folder = fr'D:\Project\2026_Nafosted-VLU\SWAT\LUC1992\{year}'
#
#
#     param_user = pd.read_csv(r"G:\My Drive\_MATHY-NLU\project\2026_NAFOSTED-VLU\best_param_flow_all.csv")
#
#     param_user = param_user.sort_values(by='TIME')
#     par1 = param_user.loc[param_user['TIME'] == 1]
#     par2 = param_user.loc[param_user['TIME'] == 2]
#     par3 = param_user.loc[param_user['TIME'] == 3]
#
#     project = SWATProject(txinout_path, working_folder, swat_exe_path, swat_param_path)
#     project.WorkingFolder.setup(overwrite=True)
#
#     w1 = project.worker(1)
#     w1.HRU.update_by_df(par1, param_name='PARAM', method='method', value='MIN', sub='SUBBASIN')
#     w1.HRU.update_by_df(par2, param_name='PARAM', method='method', value='MIN', sub='SUBBASIN')
#     w1.HRU.update_by_df(par3, param_name='PARAM', method='method', value='MIN', sub='SUBBASIN')
#
#     w1.run()
#
#     rch = [49,51,55,57,61,66,73,77]
#     out = w1.Output.read_rch("FLOW_OUTcms", rch, freq='MS')
#     date_range = project.get_date_range(freq='MS')
#
#
#     values = out['FLOW_OUTcms'].to_numpy()
#     matrix = values.reshape(-1, len(rch))
#     df1 = pd.DataFrame(matrix, index=date_range, columns=rch)
#     df1.to_csv(Path(working_folder) / f'{year}.csv')



for year in years:
    txinout_path = fr'D:\Project\2026_Nafosted-VLU\SWAT\LUC1992\{year}\TxInOut1'
    working_folder = fr'D:\Project\2026_Nafosted-VLU\SWAT\LUC1992\{year}\SEDIMENT'
    param_user = pd.read_csv(r"G:\My Drive\_MATHY-NLU\project\2026_NAFOSTED-VLU\best_param_sediment.csv")



    pars = [1,2,3]
    out_df = pd.DataFrame()
    x = 1
    for par in pars:
        project = SWATProject(txinout_path, working_folder, swat_exe_path, swat_param_path)
        project.WorkingFolder.setup(overwrite=True)
        w1 = project.worker(1)
        print(year, "|", par)
        par1 = param_user.loc[param_user['TIME'] == par]
        w1.HRU.update_by_df(par1, param_name='PARAM', method='method', value='MIN', sub='SUBBASIN')
        w1.run()

        if par == 1:
            rch = [51,55,73]
        elif par == 2:
            rch = [57]
        elif par == 3:
            rch = [77]

        out = w1.Output.read_rch("SED_OUTtons", rch, freq='MS')
        date_range = project.get_date_range(freq='MS')

        values = out['SED_OUTtons'].to_numpy()
        matrix = values.reshape(-1, len(rch))
        df1 = pd.DataFrame(matrix, index=date_range, columns=rch)
        out_df = out_df.merge(df1, left_index=True, right_index=True, how='outer')
    out_df.to_csv(Path(working_folder) / f'{year}.csv')