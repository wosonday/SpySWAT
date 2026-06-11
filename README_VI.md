# SpySWAT 🌊

**Thư viện Python để hiệu chỉnh, kiểm định và phân tích độ nhạy mô hình SWAT**

> Phiên bản tiếng Anh: [README_EN.md](README_EN.md) · Lịch sử thay đổi: [CHANGELOG.md](CHANGELOG.md)

---

## Mục lục

- [Giới thiệu](#giới-thiệu)
- [Cài đặt](#cài-đặt)
- [Khởi tạo dự án](#khởi-tạo-dự-án)
- [Định dạng tham số bắt buộc](#định-dạng-tham-số-bắt-buộc)
- [Quy trình nhanh (Recommended)](#quy-trình-nhanh-recommended)
- [Hiệu chỉnh tham số](#hiệu-chỉnh-tham-số)
- [Kiểm định](#kiểm-định)
- [Phân tích độ nhạy](#phân-tích-độ-nhạy)
- [Đọc và ghi TxtInOut](#đọc-và-ghi-txtinout)
- [Đọc kết quả SWAT](#đọc-kết-quả-swat)
- [Thống kê hiệu suất](#thống-kê-hiệu-suất)
- [Chạy song song](#chạy-song-song)
- [File tham số](#file-tham-số)
- [API Reference](#api-reference)

---

## Giới thiệu

SpySWAT là thư viện Python cho phép:

- Đọc và ghi trực tiếp vào các file TxtInOut của SWAT (định dạng fixed-width)
- Hiệu chỉnh tham số tự động: GLUE, Differential Evolution, PSO
- Chạy song song nhiều bộ tham số qua `ProcessPoolExecutor`
- Tính độ nhạy tham số từ kết quả hiệu chỉnh — **không cần chạy SWAT thêm**
- Đánh giá hiệu suất theo chuẩn Moriasi et al. (2007)

---

## Cài đặt

```bash
pip install spyswat
# hoặc từ source
git clone https://github.com/yourname/spyswat
pip install -e .
```

Yêu cầu: Python >= 3.12, numpy, pandas, scipy

---

## Khởi tạo dự án

```python
from spyswat import SWATProject

project = SWATProject(
    txinout_dir="D:/SWAT/my_project/TxtInOut",
    working_dir="D:/SWAT/workers",
    swat_exe="D:/SWAT/swat_rev688.exe",
    param_file="params.txt",
    n_parallel=8
)
```

| Tham số | Bắt buộc | Mô tả |
|---------|----------|-------|
| `txinout_dir` | Có | Đường dẫn thư mục TxtInOut |
| `working_dir` | Có | Thư mục chứa worker copies (tự tạo) |
| `swat_exe` | Có | Đường dẫn SWAT executable |
| `param_file` | Không | File định nghĩa tham số `.txt` |
| `n_parallel` | Không | Số worker song song (mặc định: 1) |

---

## Định dạng tham số bắt buộc

> **⚠️ Kể từ v0.2.1, tất cả key tham số phải dùng định dạng `name.ext`.**

Định dạng `name.ext` chỉ rõ cả tên tham số lẫn loại file SWAT cần cập nhật, tránh nhầm lẫn khi cùng tên tham số tồn tại ở nhiều loại file khác nhau.

```python
# ❌ Sai — bare name không còn được chấp nhận
{"CN2": [(75.0, "v")]}

# ✅ Đúng — luôn kèm phần mở rộng file
{"CN2.mgt": [(75.0, "v")]}
```

Bảng tham chiếu nhanh:

| Tham số | Key đúng | File SWAT |
|---------|----------|-----------|
| CN2 | `CN2.mgt` | `.mgt` (management) |
| ALPHA_BF | `ALPHA_BF.gw` | `.gw` (groundwater) |
| GW_DELAY | `GW_DELAY.gw` | `.gw` (groundwater) |
| ESCO | `ESCO.hru` | `.hru` (HRU general) |
| SOL_AWC | `SOL_AWC.sol` | `.sol` (soil) |
| SURLAG | `SURLAG.bsn` | `.bsn` (basin) |

Nếu dùng bare name, SpySWAT sẽ báo lỗi rõ ràng với gợi ý key đúng:

```
ValueError: Parameter key(s) ['CN2'] missing file extension.
Use 'name.ext' format, e.g. 'CN2.mgt', 'ALPHA_BF.gw', 'ESCO.hru'.
```

---

## Quy trình nhanh (Recommended)

Từ phiên bản 0.2.0, `SWATCalibration.analyze()` thực hiện toàn bộ workflow trong một lệnh:
**GLUE parallel → best params → sensitivity → đánh giá** — chỉ từ N lần chạy SWAT.

```python
import pandas as pd
from spyswat import SWATProject
from spyswat.swat_calib.analysis import SWATCalibration

project = SWATProject(
    txinout_dir="path/TxtInOut",
    working_dir="path/workers",
    swat_exe="path/swat.exe",
    param_file="params.txt",
    n_parallel=8
)

obs = pd.read_csv("observed_flow.csv", index_col="date", parse_dates=True)["flow"]

# Key phải dùng name.ext để xác định đúng file cần cập nhật
param_ranges = {
    "CN2.mgt":      (35, 98),
    "ALPHA_BF.gw":  (0.0, 1.0),
    "GW_DELAY.gw":  (30, 450),
    "ESCO.hru":     (0.01, 1.0),
    "SOL_AWC.sol":  (0.01, 0.5),
}

calib = SWATCalibration(project)
result = calib.analyze(
    param_ranges=param_ranges,
    observed_series=obs,
    n_samples=1000,
    threshold=0.5,
    metric="nse"
)

print(f"Best NSE:  {result['best_score']:.3f}")
print(result['best_params'])
print(result['sensitivity'])
print(result['performance'])
```

Luồng bên trong `analyze()`:

```
1000 mẫu LHS
      |
      v
run_batch (8 worker song song)
      |
      v
1000 (params, score)
   /       |         \
best    sensitivity   behavioral
params  (Spearman,    (NSE >= 0.5)
        0 SWAT thêm)
```

---

## Hiệu chỉnh tham số

### GLUE – Monte Carlo song song

```python
from spyswat.swat_calib.analysis import SWATCalibration

calib = SWATCalibration(project)
calib._manager.setup_parallel(overwrite=True)

result = calib.glue_analysis(
    param_ranges=param_ranges,   # key dạng name.ext
    observed_series=obs,
    n_samples=1000,
    threshold=0.5,
    metric="nse",
    output_variable="FLOW_OUTcms",
    reach_id=1
)

print(result["all_results"])
print(result["behavioral_results"])
print(f"Behavioral ratio: {result['behavioral_ratio']:.1%}")
```

### Differential Evolution

```python
result = calib.optimize(
    param_ranges=param_ranges,
    observed_series=obs,
    method="differential_evolution",
    metric="nse",
    max_iter=100,
    reach_id=1
)

print(result["best_parameters"])
print(f"Best NSE: {result['best_objective_value']:.4f}")
```

### Một iteration thủ công

```python
from spyswat.swat_calib.calibration import CalibrationManager

manager = CalibrationManager(project)
score = manager.run_iteration(
    param_dict={"CN2.mgt": [(75.0, "v")], "ALPHA_BF.gw": [(0.5, "v")]},
    observed=obs,
    metric="nse",
    reach_id=1
)
print(f"NSE = {score:.4f}")
```

---

## Kiểm định

```python
# best_params từ analyze() đã ở dạng name.ext, dùng trực tiếp
best = result["best_params"]
project.HRU.update_params(best)
project.run()

# Đọc output giai đoạn kiểm định
sim = project.Output.read_rch(
    columns=["RCH", "MON", "FLOW_OUTcms"],
    reach_id=1
)["FLOW_OUTcms"]

obs_val = obs["2010-01-01":"2015-12-31"]
sim_val = sim["2010-01-01":"2015-12-31"]

stats  = project.Statistic.calculate_statistics(obs_val, sim_val)
rating = project.Statistic.evaluate_performance(obs_val, sim_val)
print(stats)   # {'nse': 0.71, 'kge': 0.68, ...}
print(rating)  # {'nse': 'Good', ...}
```

---

## Phân tích độ nhạy

### Từ kết quả GLUE (khuyến nghị – không chạy SWAT thêm)

```python
sensitivity = project.Statistic.sensitivity_from_results(
    results_df=result["all_results"],
    metric="nse",
    method="spearman"   # hoặc "prcc"
)
print(sensitivity)
# parameter    sensitivity_index  rank
# ALPHA_BF.gw       0.83            1
# CN2.mgt           0.61            2
# GW_DELAY.gw       0.45            3
```

Hai phương pháp tính sensitivity:

| method | Tên đầy đủ | Ưu điểm |
|--------|-----------|---------|
| `spearman` | Spearman rank correlation | Nhanh, không giả định tuyến tính |
| `prcc` | Partial Rank Correlation Coefficient | Loại bỏ ảnh hưởng chéo giữa tham số |

### OAT – One-At-a-Time (song song)

```python
from spyswat.swat_calib.analysis import SWATSensitivity

sens = SWATSensitivity(project)
oat_df, indices = sens.one_at_a_time(
    param_ranges=param_ranges,   # key dạng name.ext
    n_steps=10,
    observed_series=obs,
    metric="nse"
)
print(indices)
```

### Morris Method (song song)

```python
morris = sens.morris_method(
    param_ranges=param_ranges,
    n_trajectories=10,
    observed_series=obs,
    metric="nse"
)
print(morris["morris_indices"])
```

---

## Đọc và ghi TxtInOut

### Cập nhật tham số HRU

```python
# Key phải có phần mở rộng file để xác định đúng loại file cần ghi
project.HRU.update_params({
    "CN2.mgt":      [(75.0, "v")],    # v = set trực tiếp
    "ALPHA_BF.gw":  [(0.5,  "v")],
    "ESCO.hru":     [(0.1,  "r")],    # r = nhân (1 + val)
    "SOL_AWC.sol":  [(0.05, "add")],  # add = cộng thêm
})
```

Ba phương thức cập nhật:

| Mã | Công thức | Ý nghĩa |
|----|-----------|---------|
| `v` / `replace` | `new = val` | Gán trực tiếp |
| `r` / `relative` | `new = old × (1 + val)` | Thay đổi tương đối |
| `add` | `new = old + val` | Cộng thêm |

### Cập nhật nhiều pass (subbasin filter)

```python
project.HRU.update_params({
    "CN2.mgt": [
        (75.0, "v", [1, 2, 3]),   # subbasin 1-3: gán 75
        (80.0, "v", [4, 5]),      # subbasin 4-5: gán 80
    ]
})
```

### Đọc giá trị hiện tại

```python
values = project.read_params_values(["CN2.mgt", "ALPHA_BF.gw", "ESCO.hru"])
```

---

## Đọc kết quả SWAT

```python
# output.rch
rch = project.Output.read_rch(
    columns=["RCH", "MON", "FLOW_OUTcms", "SED_OUTtons"],
    reach_id=1
)

# output.hru
hru = project.Output.read_hru(
    columns=["LULC", "HRU", "MON", "ET", "SURQ_GEN"]
)

# output.sub
sub = project.Output.read_sub(columns=["SUB", "MON", "PRECIP", "SURQ"])

# output.sed
sed = project.Output.read_sed()

# watout.dat
wat = project.Output.read_watout()
```

Biến output.rch thường dùng:

| Biến | Đơn vị | Mô tả |
|------|--------|-------|
| `FLOW_OUTcms` | m³/s | Lưu lượng ra |
| `SED_OUTtons` | tấn | Bùn cát ra |
| `NO3_OUTkg` | kg | Nitrate |
| `ORG_N_kg` | kg | Nitơ hữu cơ |

---

## Thống kê hiệu suất

```python
stats  = project.Statistic.calculate_statistics(obs, sim)
rating = project.Statistic.evaluate_performance(obs, sim)
```

Thang đánh giá NSE (Moriasi et al., 2007):

| NSE | Đánh giá |
|-----|----------|
| > 0.75 | Very Good |
| 0.65–0.75 | Good |
| 0.50–0.65 | Satisfactory |
| 0.40–0.50 | Acceptable |
| ≤ 0.40 | Unsatisfactory |

---

## Chạy song song

SpySWAT dùng `ProcessPoolExecutor` với mô hình worker pool — N bản sao TxtInOut, mỗi worker dùng bản sao riêng.

```
1000 mẫu, 8 workers → 125 batch × T_swat ≈ tăng tốc 8×

Batch 1:   [m1  m2  m3  m4  m5  m6  m7  m8]  ← song song
Batch 2:   [m9  m10 m11 m12 m13 m14 m15 m16]
...
Batch 125: [m993..m1000]
```

Setup thủ công:

```python
project.WorkingFolder.setup(overwrite=True)

worker_dirs = project.WorkingFolder.run_parallel(
    swat_exe="path/swat.exe",
    param_sets=[
        {"CN2.mgt": [(70.0, "v")]},
        {"CN2.mgt": [(75.0, "v")]},
        {"CN2.mgt": [(80.0, "v")]},
    ]
)

for i in range(3):
    flow = project.worker(i + 1).Output.read_rch(
        columns=["RCH", "MON", "FLOW_OUTcms"], reach_id=1
    )["FLOW_OUTcms"]
    print(flow.mean())
```

---

## File tham số

```
# name    ext     line  col_start  col_end  round  vmin   vmax
CN2       .mgt    8     3          12       1      35.0   98.0
ALPHA_BF  .gw     6     3          12       3      0.0    1.0
GW_DELAY  .gw     5     3          12       1      30.0   450.0
ESCO      .hru    9     3          12       3      0.01   1.0
SOL_AWC   .sol    0     0          0        3      0.01   0.5
```

Key khi dùng trong code = `name + ext`, ví dụ: `CN2.mgt`, `ALPHA_BF.gw`, `ESCO.hru`.

---

## API Reference

### SWATProject

```
project.HRU.update_params(param_dict)        # key phải dùng name.ext
project.HRU.update_by_df(df)                 # cột param phải dùng name.ext
project.read_params_values(param_list)        # list phải dùng name.ext
project.run()
project.get_date_range(freq='D')
project.worker(index)
project.Output.read_rch / read_hru / read_sub / read_sed / read_watout
project.Statistic.calculate_statistics(obs, sim)
project.Statistic.evaluate_performance(obs, sim)
project.Statistic.sensitivity_from_results(df, metric, method)   # v0.2.0
project.FileCIO.get_date_range_sim(freq)
project.WorkingFolder.setup(overwrite)
project.WorkingFolder.run_parallel(exe, param_sets)
project.info()
```

### CalibrationManager

```
CalibrationManager(project)
  .setup_parallel(overwrite=False)
  .run_iteration(param_dict, obs, metric, ...)   # param_dict dùng name.ext
  .run_batch(param_sets, obs, metric, ...)       # v0.2.0, param_sets dùng name.ext
```

### SWATCalibration

```
SWATCalibration(project)
  .analyze(param_ranges, obs, n_samples, ...)    # v0.2.0, param_ranges dùng name.ext
  .glue_analysis(param_ranges, obs, n_samples)   # param_ranges dùng name.ext
  .optimize(param_ranges, obs, method, ...)
```

### SWATSensitivity

```
SWATSensitivity(project)
  .one_at_a_time(param_ranges, n_steps, obs)     # param_ranges dùng name.ext
  .morris_method(param_ranges, n_trajectories)   # param_ranges dùng name.ext
```

---

## Tài liệu tham khảo

- Moriasi et al. (2007). *Model Evaluation Guidelines.* ASABE, 50(3), 885–900.
- Beven & Binley (1992). *GLUE.* Hydrological Processes, 6(3), 279–298.
- Saltelli et al. (2008). *Global Sensitivity Analysis: The Primer.* Wiley.
- Helton & Davis (2003). *Latin hypercube sampling.* Reliability Engineering & System Safety, 81(1), 23–69.

---

*SpySWAT v0.2.1 · [CHANGELOG](CHANGELOG.md) · [English](README_EN.md)*
