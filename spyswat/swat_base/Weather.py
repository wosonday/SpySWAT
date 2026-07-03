import os
import logging
from typing import Optional

import numpy as np
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


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
        master = self.masterFile.sort_values(by='ID') if sort else self.masterFile
        n_stations = len(master)
        logger.info(f"[writePcp] Output: {fname} | {n_stations} stations | sort={sort}")

        with open(fname, 'w') as f:
            # Station
            f.write("Station  ")
            for NAME in master.NAME:
                f.write(f"{NAME},")
            f.write("\n")

            # Lat — mỗi trạm chiếm 5 ký tự (f5.1)
            f.write('Lati   ')
            for stn in master.LAT:
                f.write(f"{stn:5.1f}")
            f.write("\n")

            #  Long — mỗi trạm chiếm 5 ký tự (f5.1)
            f.write("Long   ")
            for stn in master.LONG:
                f.write(f"{stn:5.1f}")
            f.write("\n")

            # Elevation (i5 — integer)
            f.write("Elev   ")
            for stn in master.ELEVATION:
                f.write(f"{int(stn):5d}")
            f.write("\n")

            # Dòng 5+: YYYYDDD + N cột mưa (f5.1 mỗi cột)
            data = []
            date_start = set()
            for NAME in master.NAME:
                stn_path = f"{self._parent}/{NAME}.txt"
                logger.debug(f"[writePcp] Reading station: {stn_path}")
                file = np.loadtxt(stn_path)
                date = file[0].astype(int).astype(str)
                df   = file[1:]
                logger.debug(f"[writePcp]   {NAME}: start={date}, rows={len(df)}")
                data.append(df)
                date_start.add(date)

            # Validate: all stations must have same start date
            if len(date_start) != 1:
                logger.error(
                    f"[writePcp] Mismatched start dates across stations: {date_start}. "
                    f"Expected exactly 1 unique date."
                )
                raise ValueError(
                    f"All PCP stations must share the same start date. "
                    f"Found {len(date_start)} distinct dates: {date_start}"
                )

            # Validate: all stations must have same number of records
            lengths = [len(d) for d in data]
            if len(set(lengths)) != 1:
                for name, length in zip(master.NAME, lengths):
                    logger.error(f"[writePcp]   {name}: {length} records")
                raise ValueError(
                    f"All PCP stations must have the same number of records. "
                    f"Found lengths: {dict(zip(self.masterFile.NAME, lengths))}"
                )

            data_all = np.stack(data).T
            logger.info(f"[writePcp] Data matrix: {data_all.shape} (days × stations)")

            date = datetime.strptime(str(list(date_start)[0]), "%Y%m%d")
            date_range = pd.date_range(date, periods=data_all.shape[0], freq="D").strftime('%Y%j')
            logger.info(f"[writePcp] Date range: {date_range[0]} → {date_range[-1]} ({len(date_range)} days)")

            # Warn if any value exceeds fixed-width format limit
            max_val = data_all.max()
            if max_val >= 1000.0:
                logger.warning(
                    f"[writePcp] Max PCP value = {max_val:.1f} mm — exceeds 05.1f format (max 999.9). "
                    f"Output file may have corrupted columns."
                )

            for i, date in enumerate(date_range):
                f.write(f"{date}")
                for val in data_all[i]:
                    f.write(f"{val:05.1f}")
                f.write("\n")

        logger.info(f"[writePcp] Done — wrote {fname}")
        return fname

    def writeTmp(self, txtInOut, fileIndex=1, sort: bool = False):
        fname = os.path.join(txtInOut, f"Tmp{fileIndex}.Tmp")
        master = self.masterFile.sort_values(by='ID') if sort else self.masterFile
        n_stations = len(master)
        logger.info(f"[writeTmp] Output: {fname} | {n_stations} stations | sort={sort}")

        with open(fname, 'w') as f:
            # Station
            f.write("Station  ")
            for NAME in master.NAME:
                f.write(f"{NAME},")
            f.write("\n")

            # Lat — mỗi trạm chiếm 5 ký tự (f5.1)
            f.write('Lati   ')
            for stn in master.LAT:
                f.write(f"{stn:11.1f}")
            f.write("\n")

            #  Long — mỗi trạm chiếm 5 ký tự (f5.1)
            f.write("Long   ")
            for stn in master.LONG:
                f.write(f"{stn:11.1f}")
            f.write("\n")

            # Elevation (i5 — integer)
            f.write("Elev   ")
            for stn in master.ELEVATION:
                f.write(f"{int(stn):11d}")
            f.write("\n")

            # Dòng 5+: YYYYDDD + N cột nhiệt độ (f5.1 mỗi cột)
            data_max = []
            data_min = []
            date_start = set()
            for NAME in master.NAME:
                stn_path = f"{self._parent}/{NAME}.txt"
                logger.debug(f"[writeTmp] Reading station: {stn_path}")

                with open(stn_path, 'r') as f_in:
                    first_line = f_in.readline().strip()

                file = np.loadtxt(stn_path, delimiter=',', skiprows=1)
                date = str(int(first_line))
                # File TMP format: col0 = Tmin, col1 = Tmax
                df_min   = file[:, 0]
                df_max   = file[:, 1]
                logger.debug(f"[writeTmp]   {NAME}: start={date}, rows={len(df_max)}, "
                             f"Tmin=[{df_min.min():.1f},{df_min.max():.1f}], "
                             f"Tmax=[{df_max.min():.1f},{df_max.max():.1f}]")

                data_max.append(df_max)
                data_min.append(df_min)

                date_start.add(date)

            # Validate: all stations must have same start date
            if len(date_start) != 1:
                logger.error(
                    f"[writeTmp] Mismatched start dates across stations: {date_start}. "
                    f"Expected exactly 1 unique date."
                )
                raise ValueError(
                    f"All TMP stations must share the same start date. "
                    f"Found {len(date_start)} distinct dates: {date_start}"
                )

            # Validate: all stations must have same number of records
            lengths = [len(d) for d in data_max]
            if len(set(lengths)) != 1:
                for name, length in zip(master.NAME, lengths):
                    logger.error(f"[writeTmp]   {name}: {length} records")
                raise ValueError(
                    f"All TMP stations must have the same number of records. "
                    f"Found lengths: {dict(zip(self.masterFile.NAME, lengths))}"
                )

            data_all_max = np.stack(data_max).T
            data_all_min = np.stack(data_min).T
            logger.info(f"[writeTmp] Data matrix: {data_all_max.shape} (days × stations)")

            start_date = datetime.strptime(str(list(date_start)[0]), "%Y%m%d")
            date_range = pd.date_range(start_date, periods=data_all_max.shape[0], freq="D").strftime('%Y%j')
            logger.info(f"[writeTmp] Date range: {date_range[0]} → {date_range[-1]} ({len(date_range)} days)")

            # Warn if Tmax < Tmin for any day (data quality check)
            bad_rows = np.where(data_all_max < data_all_min)
            if len(bad_rows[0]) > 0:
                n_bad = len(bad_rows[0])
                logger.warning(
                    f"[writeTmp] {n_bad} records where Tmax < Tmin detected. "
                    f"First occurrence: day index {bad_rows[0][0]}, station index {bad_rows[1][0]}"
                )

            for i, date in enumerate(date_range):
                f.write(f"{date}")
                for val_max, val_min in zip(data_all_max[i], data_all_min[i]):
                    f.write(f"{val_max:05.1f}{val_min:05.1f}")

                f.write("\n")

        logger.info(f"[writeTmp] Done — wrote {fname}")
        return fname
