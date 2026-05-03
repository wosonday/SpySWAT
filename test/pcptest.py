from swat_calib.io import Weather
from swat_calib.core import TxInOut

import pandas as pd



txinout = TxInOut('data/TxtInOut')
pcp = txinout.get_weather_file('pcp')
print(pd.read_csv(pcp))


cop = r'D:\SWAT-model\ArcSWAT\SWAT\ht_caupha\caupha\Scenarios\Default\TxtInOut\pcp1.pcp'

Weather.copy(cop, txinout.directory)
pcp = txinout.get_weather_file('pcp')

print(pd.read_csv(pcp))