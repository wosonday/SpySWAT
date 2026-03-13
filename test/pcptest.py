from swat_toolkit.io.weather import Weather
from swat_toolkit.core.txinout import TxInOut

import pandas as pd

txinout = TxInOut('data/TxtInOut')

pcp = txinout.get_weather_file('pcp')


print(pd.read_csv(pcp))