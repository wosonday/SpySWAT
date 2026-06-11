# SpySWAT

**SpySWAT** là thư viện Python để đọc, chỉnh sửa, chạy và hiệu chỉnh mô hình **SWAT (Soil and Water Assessment Tool)** thông qua thư mục `TxtInOut`. Thư viện cung cấp API lập trình thay thế cho việc chỉnh sửa file SWAT thủ công, hỗ trợ hiệu chỉnh tự động, chạy song song, và đánh giá hiệu năng mô hình.

---

## Mục lục

- [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
- [Cài đặt](#cài-đặt)
- [Quick Start — 5 phút](#quick-start--5-phút)
- [Kiến trúc](#kiến-trúc)
- [API Reference](#api-reference)
  - [SWATProject](#swatproject)
  - [TxInOut](#txinout)
  - [HRUManager — project.HRU](#hrumanager--projecthru)
  - [OutputFileManager — project.Output](#outputfilemanager--projectoutput)
  - [FileCIO — project.FileCIO](#filecio--projectfilecio)
  - [WorkingFolderManager — project.WorkingFolder](#workingfoldermanager--projectworkingfolder)
  - [SWATAnalysis — project.Statistic](#swatanalysis--projectstatistic)
  - [SWATParam](#swatparam)
- [Cấu trúc file tham số](#cấu-trúc-file-tham-số)
- [Các biến output được hỗ trợ](#các-biến-output-được-hỗ-trợ)
- [Phương pháp hiệu chỉnh](#phương-pháp-hiệu-chỉnh)
- [Chạy song song](#chạy-song-song)

---

## Yêu cầu hệ thống

- Python ≥ 3.10
- pandas, numpy, matplotlib
- scipy (cho hiệu chỉnh tự động)
- SWAT executable (`.exe`) phù hợp với phiên bản TxtInOut của bạn

---

## Cài đặt

```bash
# Clone repository
git clone <repo_url>
cd SpySWAT

# Cài đặt dependencies
pip install pandas numpy matplotlib scipy
```

---

## Quick Start — 5 phút

### 1. Khởi tạo project

```python
from spyswat import SWATProject

project = SWATProject(
    txinout_dir = r"D:\MyProject\TxtInOut",    # thư mục TxtInOut của SWAT
    working_dir = r"D:\MyProject\working",      # thư mục làm việc (chạy song song)
    swat_exe    = r"D:\tools\swat_695.exe",     # đường dẫn đến SWAT executable
    param_file  = r"D:\MyProject\swatParam.txt" # file định nghĩa tham số
)

# Xem thông tin project
project.info()
# TxtInOut: D:\MyProject\TxtInOut
# Found 47 HRUs in 13 subbasins
```

### 2. Đọc output mô phỏng

```python
import pandas as pd

# Lấy dải thời gian mô phỏng
date_range = project.get_date_range(freq='D')  # hoặc 'MS' cho tháng

# Đọc output reach (output.rch)
df_rch = project.Output.read_rch(
    columns  = ['RCH', 'MON', 'FLOW_OUTcms'],
    reach_id = 8
)

# Gắn index thời gian
df_rch.index = date_range
print(df_rch['FLOW_OUTcms'].head())
```

### 3. Cập nhật tham số và chạy lại

```python
# Cập nhật tham số — 3 phương pháp:
#   'v' hoặc 'replace' : gán trực tiếp giá trị
#   'r' hoặc 'relative': nhân (1 + value), tức thay đổi tương đối
#   'add'              : cộng thêm value vào giá trị hiện tại

project.HRU.update_params({
    'CN2':      [(75,   'v')],    # gán CN2 = 75 cho toàn lưu vực
    'ESCO':     [(0.95, 'r')],    # tăng ESCO thêm 95%
    'ALPHA_BF': [(0.5,  'v')],    # gán ALPHA_BF = 0.5
})

# Chạy SWAT
project.run()
```

### 4. Đánh giá hiệu năng

```python
obs = pd.read_csv("observed_flow.csv", index_col='date', parse_dates=['date'])

df_sim = project.Output.read_rch(['RCH', 'MON', 'FLOW_OUTcms'], reach_id=8)
df_sim.index = date_range

# Căn chỉnh thời gian
common = obs.index.intersection(df_sim.index)
stats = project.Statistic.calculate_statistics(
    observed  = obs.loc[common, 'discharge'],
    simulated = df_sim.loc[common, 'FLOW_OUTcms']
)

print(stats)
# {'nse': 0.72, 'r2': 0.81, 'rmse': 14.3, 'pbias': -5.2, 'kge': 0.69}

# Đánh giá định tính (theo Moriasi et al., 2007)
ratings = project.Statistic.evaluate_performance(
    obs.loc[common, 'discharge'],
    df_sim.loc[common, 'FLOW_OUTcms']
)
# {'nse': 'Good', 'pbias': 'Very Good', 'rsr': 'Good'}
```

---

## Kiến trúc

```
SWATProject  (facade — điểm vào duy nhất)
│
├── TxInOut               → Filesystem abstraction cho thư mục TxtInOut
│   └── FileMapping       → Ánh xạ tên file theo loại (HRU, watershed, output...)
│
├── HRUManager            → Đọc/ghi tham số vào các file HRU
│   ├── SWATParam         → Định nghĩa tham số (line, col_start, col_end, vmin, vmax)
│   ├── HRURead           → Đọc giá trị tham số theo vị trí cột
│   └── HRUWriter         → Ghi đè giá trị tham số (fixed-width, positional edit)
│
├── OutputFileManager     → Đọc các file output SWAT (output.rch, .hru, .sub, ...)
│   ├── OutputFileReader  → Parser core — dùng column mapping để đọc fixed-width
│   ├── SWATReaderCache   → Cache DataFrame theo file path
│   └── *Mapping classes  → Ánh xạ tên cột → (col_start, col_end)
│
├── FileCIO               → Đọc/cập nhật file.cio (thời gian mô phỏng, tần suất)
│
├── SWATAnalysis          → Tính toán chỉ số hiệu năng (NSE, KGE, PBIAS, R², RMSE)
│
├── SWATRun               → Gọi SWAT executable qua subprocess
│
└── WorkingFolderManager  → Tạo và quản lý các worker directory cho chạy song song
```

**Luồng dữ liệu điển hình:**

```
file.cio → FileCIO → date_range
TxtInOut/*.hru/*.sol/*.mgt → HRUWriter → cập nhật tham số
SWATRun → chạy SWAT executable
output.rch → OutputFileReader → DataFrame → SWATAnalysis
```

---

## API Reference

### SWATProject

Điểm vào chính của thư viện.

```python
SWATProject(
    txinout_dir : str | Path,           # thư mục TxtInOut
    working_dir : str | Path,           # thư mục làm việc (cho parallel)
    swat_exe    : str | Path,           # đường dẫn SWAT executable
    param_file  : str | None = None,    # file swatParam.txt
    n_parallel  : int = 1               # số worker cho chạy song song
)
```

| Thuộc tính / Phương thức | Mô tả |
|--------------------------|-------|
| `project.HRU` | `HRUManager` — đọc/ghi tham số |
| `project.Output` | `OutputFileManager` — đọc output mô phỏng |
| `project.FileCIO` | `FileCIO` — đọc/cập nhật thời gian mô phỏng |
| `project.Statistic` | `SWATAnalysis` — tính chỉ số hiệu năng |
| `project.WorkingFolder` | `WorkingFolderManager` — quản lý worker dirs |
| `project.run()` | Chạy SWAT executable tại TxtInOut |
| `project.get_date_range(freq)` | Trả về `pd.DatetimeIndex` từ file.cio |
| `project.info()` | In thông tin project |
| `project.worker(index)` | Lấy `SWATProject` của worker thứ `index` (1-based) |

---

### TxInOut

Abstraction layer cho thư mục TxtInOut. Được tạo tự động khi khởi tạo `SWATProject`.

```python
from spyswat.swat_calib.core import TxInOut
txinout = TxInOut(r"D:\MyProject\TxtInOut")
```

| Phương thức | Mô tả |
|-------------|-------|
| `txinout.get_hru_file(ext, subbasin_num=None, hru_num=None)` | Lấy file HRU theo extension và filter |
| `txinout.get_all_hru_files(ext)` | Lấy tất cả file có extension, sorted |
| `txinout.get_watershed_file(ext)` | Lấy file watershed level (basins.bsn, file.cio...) |
| `txinout.get_output_file(ext)` | Lấy file output (output.rch, output.hru...) |
| `txinout.get_weather_file(ext, index)` | Lấy file thời tiết (pcp1.pcp, tmp1.tmp...) |
| `txinout.get_resevoir(ext, reservoir_id)` | Lấy file hồ chứa |
| `txinout.number_hru` | Tổng số HRU trong lưu vực |
| `txinout.number_sub` | Tổng số tiểu lưu vực |
| `txinout.hru_info` | List dict chứa thông tin từng HRU (Subbasin, HRU, Luse, Soil, Slope) |

---

### HRUManager — `project.HRU`

Quản lý đọc/ghi tham số SWAT vào các file trong TxtInOut.

#### `update_params(param_dict, subbasin=None)`

Cập nhật một hoặc nhiều tham số. Mỗi tham số nhận một tuple `(value, method)` hoặc list các tuple (multi-pass).

```python
project.HRU.update_params({
    # Gán giá trị trực tiếp (replace)
    'CN2':      [(75.0, 'v')],

    # Thay đổi tương đối: new = old * (1 + value)
    'SOL_AWC':  [(-0.10, 'r')],

    # Cộng thêm
    'GW_DELAY': [(5.0, 'add')],

    # Chỉ áp dụng cho subbasin 3 và 5
    'ESCO':     [(0.8, 'v', [3, 5])],
})
```

**Các phương pháp cập nhật:**

| Method | Alias | Công thức |
|--------|-------|-----------|
| `'replace'` | `'v'` | `new = value` |
| `'relative'` | `'r'` | `new = old × (1 + value)` |
| `'add'` | `'add'` | `new = old + value` |

Giá trị sau khi tính toán được clamp vào `[vmin, vmax]` theo định nghĩa trong file tham số.

#### `update_by_df(df, param_name, method, value, sub)`

Cập nhật hàng loạt tham số từ một `DataFrame` — tiện dụng khi load từ CSV.

```python
df = pd.read_csv('calib_params.csv')
# Cột yêu cầu: param, value, method
# Cột tùy chọn: subbasin (để lọc theo tiểu lưu vực)
project.HRU.update_by_df(df)
```

#### `read_muti_hru_param_values(param_list)`

Đọc giá trị hiện tại của các tham số từ tất cả HRU.

```python
df = project.read_params_values(['CN2', 'ESCO', 'SOL_AWC'])
# Trả về DataFrame: columns = ['hru', 'CN2', 'ESCO', 'SOL_AWC']
```

---

### OutputFileManager — `project.Output`

Đọc các file output của SWAT. Cache tự động theo file path.

#### `read_rch(columns, reach_id, freq)`

Đọc `output.rch` — kết quả tại các đoạn sông.

```python
# Đọc toàn bộ
df = project.Output.read_rch()

# Đọc cột chọn lọc + lọc reach
df = project.Output.read_rch(
    columns  = ['RCH', 'MON', 'FLOW_OUTcms', 'SED_OUTtons'],
    reach_id = [3, 8],   # có thể là int hoặc list
    freq     = 'D'       # 'D' = ngày, 'MS' = tháng
)
```

#### `read_hru(columns, hru_id)`

Đọc `output.hru` — kết quả theo HRU.

```python
df = project.Output.read_hru(
    columns = ['HRU', 'SUB', 'MON', 'ET', 'WYLD', 'SURQ_GEN'],
    hru_id  = [1, 5, 12]
)
```

#### `read_sub(columns, sub_id)`

Đọc `output.sub` — kết quả theo tiểu lưu vực.

```python
df = project.Output.read_sub(
    columns = ['SUB', 'MON', 'PRECIP', 'ET', 'SURQ', 'WYLD'],
    sub_id  = 3
)
```

#### `read_watout(columns)`

Đọc `watout.dat` — lưu lượng tại outlet của toàn lưu vực.

```python
df = project.Output.read_watout(['YEAR', 'DAY', 'FLOW'])
```

---

### FileCIO — `project.FileCIO`

Đọc và cập nhật file điều khiển `file.cio`.

```python
# Lấy date range từ file.cio
date_range = project.FileCIO.get_date_range_sim(freq='D')
# pd.DatetimeIndex: từ năm bắt đầu đến năm kết thúc (đã bỏ warm-up)

# Lấy date range bao gồm cả năm warm-up
date_range_full = project.FileCIO.get_date_range_sim(freq='D', year_start_non_skip=True)

# Cập nhật thời gian mô phỏng theo dữ liệu thời tiết (đọc từ file pcp)
project.FileCIO.update(freq='D')    # cập nhật NBYR, IYR, IDAL + tần suất ngày
project.FileCIO.update(freq='MS')   # tần suất tháng
```

| Thuộc tính | Mô tả |
|------------|-------|
| `project.FileCIO.begin_year` | Năm bắt đầu mô phỏng (IYR) |
| `project.FileCIO.year_start` | Năm bắt đầu sau khi bỏ warm-up |
| `project.FileCIO.year_end` | Năm kết thúc mô phỏng |

---

### WorkingFolderManager — `project.WorkingFolder`

Tạo và quản lý nhiều bản sao TxtInOut cho chạy song song.

```python
# Cần khởi tạo SWATProject với n_parallel > 1
project = SWATProject(
    txinout_dir = r"D:\MyProject\TxtInOut",
    working_dir = r"D:\MyProject\working",
    swat_exe    = r"D:\tools\swat_695.exe",
    param_file  = r"D:\MyProject\swatParam.txt",
    n_parallel  = 4
)

# Tạo 4 worker directories (copy từ TxtInOut gốc)
project.WorkingFolder.setup(overwrite=True)

# Chuẩn bị bộ tham số cho từng worker
param_sets = [
    {'CN2': [(70, 'v')], 'ESCO': [(0.8,  'v')]},
    {'CN2': [(75, 'v')], 'ESCO': [(0.85, 'v')]},
    {'CN2': [(80, 'v')], 'ESCO': [(0.90, 'v')]},
    {'CN2': [(85, 'v')], 'ESCO': [(0.95, 'v')]},
]

# Chạy song song
project.WorkingFolder.run_parallel(
    swat_exe   = r"D:\tools\swat_695.exe",
    param_sets = param_sets
)

# Đọc output từng worker
worker1 = project.worker(1)
df_w1 = worker1.Output.read_rch(['RCH', 'MON', 'FLOW_OUTcms'], reach_id=8)

# Dọn dẹp
project.WorkingFolder.cleanup()
```

---

### SWATAnalysis — `project.Statistic`

Tính toán các chỉ số thống kê đánh giá hiệu năng mô hình.

#### `calculate_statistics(observed, simulated, metrics, remove_nan)`

```python
stats = project.Statistic.calculate_statistics(
    observed   = obs_series,
    simulated  = sim_series,
    metrics    = ['nse', 'kge', 'r2', 'pbias', 'rmse', 'rsr'],  # None = tất cả
    remove_nan = True
)
```

**Các chỉ số hỗ trợ:**

| Chỉ số | Mô tả | Giá trị tốt |
|--------|-------|-------------|
| `nse` | Nash-Sutcliffe Efficiency | > 0.65 (Good), > 0.75 (Very Good) |
| `kge` | Kling-Gupta Efficiency | → 1 |
| `r2` | R² (hệ số xác định) | → 1 |
| `pbias` | Percent Bias (%) | \|PBIAS\| < 10 (Very Good) |
| `rmse` | Root Mean Square Error | → 0 |
| `rsr` | RMSE/StDev ratio | ≤ 0.50 (Very Good) |
| `correlation` | Hệ số tương quan Pearson | → 1 |

#### `evaluate_performance(observed, simulated)`

Đánh giá định tính theo thang của **Moriasi et al. (2007)** — *Journal of the American Water Resources Association*.

```python
ratings = project.Statistic.evaluate_performance(obs, sim)
# {'nse': 'Very Good', 'pbias': 'Good', 'rsr': 'Satisfactory'}
```

---

### SWATParam

Quản lý định nghĩa tham số SWAT từ file cấu hình.

```python
from spyswat.swat_calib.io import SWATParam

params = SWATParam(r"D:\MyProject\swatParam.txt")
p = params.get('CN2')
print(p.name, p.ext, p.line, p.start, p.end, p.vmin, p.vmax)
# CN2 .mgt 31 16 21 25.0 98.0
```

---

## Cấu trúc file tham số

File `swatParam.txt` định nghĩa vị trí và ràng buộc của từng tham số trong file SWAT. Mỗi dòng có dạng:

```
! Đây là comment, bị bỏ qua
! <Tên>.<ext>   <line>  <col_start>  <col_end>  <round>  <vmin>   <vmax>
CN2.mgt           32       17           21          0       25.0     98.0
ESCO.hru           9       17           21          3        0.0      1.0
SOL_AWC.sol       34       27           39          3        0.0      1.0
ALPHA_BF.gw        7       17           21          2        0.0      1.0
GW_DELAY.gw        6       17           21          0        0.0    500.0
```

| Trường | Mô tả |
|--------|-------|
| `Tên.ext` | Tên tham số và extension file SWAT |
| `line` | Số dòng trong file (1-indexed) |
| `col_start` | Cột bắt đầu giá trị (1-indexed) |
| `col_end` | Cột kết thúc giá trị (exclusive) |
| `round` | Số chữ số thập phân khi ghi |
| `vmin` | Giá trị tối thiểu cho phép |
| `vmax` | Giá trị tối đa cho phép |

---

## Các biến output được hỗ trợ

### output.rch — Reach / Đoạn sông

| Cột | Đơn vị | Mô tả |
|-----|--------|-------|
| `RCH` | - | Số hiệu reach |
| `MON` | - | Tháng / Ngày trong năm (≤ 12 = tháng, ≤ 366 = ngày) |
| `FLOW_INcms` | m³/s | Lưu lượng vào |
| `FLOW_OUTcms` | m³/s | Lưu lượng ra |
| `EVAPcms` | m³/s | Bốc hơi |
| `TLOSScms` | m³/s | Tổn thất thấm dọc lòng sông |
| `SED_INtons` | tấn | Bùn cát vào |
| `SED_OUTtons` | tấn | Bùn cát ra |
| `SEDCONCmg_L` | mg/L | Nồng độ bùn cát |
| `NO3_OUTkg` | kg | Nitrat ra |
| `TOT_Nkg` | kg | Tổng Nitơ |
| `TOT_Pkg` | kg | Tổng Phốt pho |
| `WTMPdegc` | °C | Nhiệt độ nước |

### output.hru — HRU level

| Cột | Đơn vị | Mô tả |
|-----|--------|-------|
| `ET` | mm | Bốc thoát hơi thực tế |
| `PET` | mm | Bốc thoát hơi tiềm năng |
| `SURQ_GEN` | mm | Dòng chảy mặt phát sinh |
| `LATQ` | mm | Dòng chảy sườn |
| `GW_Q` | mm | Dòng chảy ngầm |
| `WYLD` | mm | Tổng lượng nước sinh ra |
| `PERC` | mm | Thấm sâu |
| `GW_RCHG` | mm | Bổ cấp tầng nước ngầm nông |
| `DA_RCHG` | mm | Bổ cấp tầng nước ngầm sâu |
| `SYLD` | t/ha | Năng suất bùn cát |
| `USLE` | t/ha | Xói mòn đất (USLE) |
| `BIOM` | t/ha | Sinh khối cây trồng |
| `LAI` | - | Chỉ số diện tích lá |
| `YLD` | t/ha | Năng suất cây trồng |

### output.sub — Subbasin level

| Cột | Đơn vị | Mô tả |
|-----|--------|-------|
| `PRECIP` | mm | Lượng mưa |
| `ET` | mm | Bốc thoát hơi |
| `SW` | mm | Lượng nước trong đất |
| `SURQ` | mm | Dòng chảy mặt |
| `GW_Q` | mm | Dòng chảy ngầm |
| `WYLD` | mm | Tổng lượng nước |
| `SYLD` | t/ha | Năng suất bùn cát |

### watout.dat — Outlet toàn lưu vực

| Cột | Mô tả |
|-----|-------|
| `YEAR` | Năm |
| `DAY` | Ngày trong năm |
| `STEP` | Bước thời gian |
| `FLOW` | Lưu lượng tại outlet (m³/s) |

---

## Phương pháp hiệu chỉnh

SpySWAT tích hợp `SWATCalibration` hỗ trợ các phương pháp hiệu chỉnh tự động.

### Tối ưu hóa bằng `scipy.optimize`

```python
from spyswat.swat_calib.analysis.calibration import SWATCalibration

calib = SWATCalibration(project)

result = calib.optimize(
    param_ranges = {
        'CN2':      (60.0, 90.0),
        'ESCO':     (0.5,  1.0),
        'ALPHA_BF': (0.1,  0.9),
    },
    observed_series = obs_flow,
    method   = 'differential_evolution',   # hoặc 'nelder-mead', 'L-BFGS-B'
    metric   = 'nse',                      # 'nse', 'kge', 'r2' được maximize
    max_iter = 100,
    reach_id = 8,
)

print(result['best_parameters'])       # {'CN2': 72.3, 'ESCO': 0.87, ...}
print(result['best_objective_value'])  # 0.74 (NSE)
```

### Phân tích GLUE (Monte Carlo)

Phương pháp **Generalized Likelihood Uncertainty Estimation** để đánh giá bất định tham số (Beven & Binley, 1992).

```python
glue_result = calib.glue_analysis(
    param_ranges = {'CN2': (60, 90), 'ESCO': (0.5, 1.0)},
    observed_series = obs_flow,
    n_samples = 500,
    threshold = 0.5,    # NSE threshold để xác định behavioral parameter sets
    metric    = 'nse',
)

behavioral_df = glue_result['behavioral_results']
print(f"Behavioral ratio: {glue_result['behavioral_ratio']:.1%}")
```

---

## Chạy song song

Khi `n_parallel > 1`, `WorkingFolderManager` tạo `n` bản sao của TxtInOut trong `working_dir/TxInOut1`, `TxInOut2`, ..., mỗi bản copy chạy SWAT với tham số khác nhau trong tiến trình con riêng biệt (`ProcessPoolExecutor`). **TxtInOut gốc không bị thay đổi.**

> ⚠️ **Bắt buộc** gọi `project.WorkingFolder.setup()` trước khi dùng `run_parallel()`.

Xem ví dụ đầy đủ tại mục [WorkingFolderManager](#workingfoldermanager--projectworkingfolder).

---

## Tài liệu tham khảo

- Moriasi, D.N. et al. (2007). Model evaluation guidelines for systematic quantification of accuracy in watershed simulations. *Transactions of the ASABE*, 50(3), 885–900.
- Beven, K. & Binley, A. (1992). The future of distributed models: Model calibration and uncertainty prediction. *Hydrological Processes*, 6(3), 279–298.
- Arnold, J.G. et al. (1998). Large area hydrologic modeling and assessment part I: Model development. *Journal of the American Water Resources Association*, 34(1), 73–89.
