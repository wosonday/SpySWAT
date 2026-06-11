import os
from typing import Optional

import numpy as np
import pandas as pd
from datetime import datetime

class Weather():
    def __init__(self, masterFile):

        self.masterFile = pd.read_csv(masterFile)
        self._parent = os.path.dirname(masterFile)

    def writeWgn(self, subbasin, wgnData, txtInOut):
        wgnFile = os.path.join(txtInOut, f"{subbasin}.wgn")
        with open(wgnFile, 'w') as f:
            # Dòng header: tên trạm, lat, lon, elevation, rain_yrs
            f.write(f"{wgnData.TITLE:9}"
                   f"{wgnData.LAT:8.3f}"
                   f"{wgnData.LONG:8.3f}"
                   f"{wgnData.ELEV:8.1f}"
                   f"{wgnData.RAIN_YRS:8d}\n")
            # 12 dòng thống kê tháng (Jan → Dec)
            for month in range(1, 13):
                row = wgnData.monthlyRow(month)
                f.write(
                    f"{row.TMPMX:8.2f}"   # avg max temp (°C)
                    f"{row.TMPMN:8.2f}"   # avg min temp (°C)
                    f"{row.TMPSTDMX:8.2f}" # std dev max temp
                    f"{row.TMPSTDMN:8.2f}" # std dev min temp
                    f"{row.PCPMM:8.2f}"   # avg monthly pcp (mm)
                    f"{row.PCPSTD:8.2f}"  # std dev daily pcp
                    f"{row.PCPSKW:8.2f}"  # skew coefficient pcp
                    f"{row.PR_W1:8.4f}"   # P(wet|dry)
                    f"{row.PR_W2:8.4f}"   # P(wet|wet)
                    f"{row.PCPD:8.2f}"   # avg rainy days/month
                    f"{row.RAINHHMX:8.2f}" # max 0.5h rainfall (mm)
                    f"{row.SOLARAV:8.2f}" # avg solar rad (MJ/m²/day)
                    f"{row.DEWPT:8.2f}"   # avg dew point (°C)
                    f"{row.WNDAV:8.2f}\n"  # avg wind speed (m/s)
                )
        return wgnFile

    def writePcp(self, txtInOut, fileIndex=1, sort: bool = False):
        fname = os.path.join(txtInOut, f"pcp{fileIndex}.pcp")
        if sort:
            self.masterFile = self.masterFile.sort_values(by='ID')
        with open(fname, 'w') as f:
            # Station
            f.write("Station  ")
            for NAME in self.masterFile.NAME:
                f.write(f"{NAME},")
            f.write("\n")

            # Lat — mỗi trạm chiếm 5 ký tự (f5.1)
            f.write('Lati   ')
            for stn in self.masterFile.LAT:
                f.write(f"{stn:5.1f}")
            f.write("\n")

            #  Long — mỗi trạm chiếm 5 ký tự (f5.1)
            f.write("Long   ")
            for stn in self.masterFile.LONG:
                f.write(f"{stn:5.1f}")
            f.write("\n")

            # Elevation (i5 — integer)
            f.write("Elev   ")
            for stn in self.masterFile.ELEVATION:
                f.write(f"{int(stn):5d}")
            f.write("\n")

            # Dòng 5+: YYYYDDD + N cột mưa (f5.1 mỗi cột)
            data = []
            date_start = set()
            for NAME in self.masterFile.NAME:
                file = np.loadtxt(f"{self._parent}/{NAME}.txt")
                date = file[0].astype(int).astype(str)
                df   = file[1:]
                data.append(df)
                date_start.add(date)

            data_all = np.stack(data).T

            if len(date_start) == 1:
                date = datetime.strptime(str(list(date_start)[0]), "%Y%m%d")
                date_range = pd.date_range(date, periods=data_all.shape[0], freq="D").strftime('%Y%j')

            for i, date in enumerate(date_range):
                f.write(f"{date}")
                for val in data_all[i]:
                    f.write(f"{val:05.1f}")
                f.write("\n")

        return fname

    def writeTmp(self, txtInOut, fileIndex=1, sort: bool = False):
        fname = os.path.join(txtInOut, f"Tmp{fileIndex}.Tmp")
        if sort:
            self.masterFile = self.masterFile.sort_values(by='ID')

        with open(fname, 'w') as f:
            # Station
            f.write("Station  ")
            for NAME in self.masterFile.NAME:
                f.write(f"{NAME},")
            f.write("\n")

            # Lat — mỗi trạm chiếm 5 ký tự (f5.1)
            f.write('Lati   ')
            for stn in self.masterFile.LAT:
                f.write(f"{stn:11.1f}")
            f.write("\n")

            #  Long — mỗi trạm chiếm 5 ký tự (f5.1)
            f.write("Long   ")
            for stn in self.masterFile.LONG:
                f.write(f"{stn:11.1f}")
            f.write("\n")

            # Elevation (i5 — integer)
            f.write("Elev   ")
            for stn in self.masterFile.ELEVATION:
                f.write(f"{int(stn):11d}")
            f.write("\n")

            # Dòng 5+: YYYYDDD + N cột mưa (f5.1 mỗi cột)
            data_max = []
            data_min = []
            date_start = set()
            for NAME in self.masterFile.NAME:
                with open(f"{self._parent}/{NAME}.txt", 'r') as f_in:
                    first_line = f_in.readline().strip()

                file = np.loadtxt(f"{self._parent}/{NAME}.txt", delimiter=',', skiprows=1)
                date = str(int(first_line))
                df_max   = file[:, 0]
                df_min   = file[:, 1]

                data_max.append(df_max)
                data_min.append(df_min)

                date_start.add(date)

            data_all_max = np.stack(data_max).T
            data_all_min = np.stack(data_min).T

            if len(date_start) == 1:
                start_date = datetime.strptime(str(list(date_start)[0]), "%Y%m%d")
                date_range = pd.date_range(start_date, periods=data_all_max.shape[0], freq="D").strftime('%Y%j')

            for i, date in enumerate(date_range):
                f.write(f"{date}")
                for val_max, val_min in zip(data_all_max[i], data_all_min[i]):
                    f.write(f"{val_max:05.1f}{val_min:05.1f}")

                f.write("\n")

        return fname
