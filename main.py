from spyswat import SWATProject
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

txinout_resevoir_path = r"/mnt/d/Project/2026_MOETS/SWAT_Ba_Basin/SWAT/Bariverbasin/Scenarios/Default/TxtInOut"

swat_exe     = r"/mnt/d/RSWAT/_SWAT_RUN/Rev_695_64rel.exe"
paramfile_path= r"/mnt/d/RSWAT/swatParam.txt"
workingF     = r"/mnt/d/Project/2026_MOETS/SWAT_Ba_Basin/workingFolder"


project = SWATProject(txinout_resevoir_path, workingF , swat_exe, paramfile_path)

project.fig_viewer(red_reaches=[32,33,37,38],open_browser=False)