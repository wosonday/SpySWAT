from swat_toolkit import SWATProject

txinout_path = r'data/TxtInOut'
swat_exe_path = r"D:\RSWAT\_SWAT_RUN\swat_695.exe"
swat_param_path = r"D:\RSWAT\swatParam.txt"

project = SWATProject(txinout_path, swat_exe_path, swat_param_path)

# param11 = ['CN2']
#
# cn2 = project.read_param_values(param11)
# print(cn2)

print(project.file_cio.get_begin_year_sim())