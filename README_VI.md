# SpySWAT 🌊

**Thư viện Python cho hiệu chỉnh, kiểm định và phân tích độ nhạy mô hình SWAT**

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-73%20passed-brightgreen)]()
[![Version](https://img.shields.io/badge/version-0.2.6-orange)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

> English version: [README_EN.md](README_EN.md) · Kiến trúc chi tiết: [ARCHITECTURE.md](ARCHITECTURE.md) · Lịch sử: [CHANGELOG.md](CHANGELOG.md)

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Cài đặt](#cài-đặt)
- [Thiết lập dự án](#thiết-lập-dự-án)
- [Định dạng tham số bắt buộc](#định-dạng-tham-số-bắt-buộc)
- [Khởi động nhanh](#khởi-động-nhanh)
- [Hiệu chỉnh](#hiệu-chỉnh)
- [Fig Viewer](#fig-viewer--sơ-đồ-lưu-vực-tương-tác)
- [Kiểm định](#kiểm-định)
- [Phân tích độ nhạy](#phân-tích-độ-nhạy)
- [Đọc/ghi TxtInOut](#đọcghi-txtinout)
- [Đọc kết quả SWAT](#đọc-kết-quả-swat)
- [Thống kê hiệu suất](#thống-kê-hiệu-suất)
- [Chạy song song](#chạy-song-song)
- [API Reference](#api-reference)
- [Tài liệu tham khảo](#tài-liệu-tham-khảo)

---

## Tổng quan

SpySWAT cung cấp:

- Đọc/ghi trực tiếp file TxtInOut của SWAT (định dạng fixed-width)
- Hiệu chỉnh tham số tự động: **GLUE**, **DDS**, **Parallel DE**, **PSO**
- Chạy song song nhiều bộ tham số qua `ProcessPoolExecutor`
- Phân tích độ nhạy từ kết quả GLUE — **không tốn thêm lần chạy SWAT**
- Đánh giá hiệu suất theo Moriasi et al. (2007)
- Tính dải bất định 95PPU với p-factor và r-factor

---

## Cài đặt

```bash
pip install spyswat
# hoặc từ source:
git clone https://github.com/wosonday/SpySWAT.git
pip install -e .
```

Yêu cầu: Python ≥ 3.12, numpy, pandas, scipy

---

## Thiết lập dự án

```python
from spyswat import SWATProject

project = SWATProject(
    txinout_dir = "D:/SWAT/TxtInOut",
    working_dir = "D:/SWAT/workspace",
    swat_exe    = "D:/SWAT/swat2012.exe",
    param_file  = "D:/SWAT/params.txt",
    n_parallel  = 8
)
```

| Tham số | Bắt buộc | Mô tả |
|---------|----------|-------|
| `txinout_dir` | ✓ | Đường dẫn tới thư mục TxtInOut |
| `working_dir` | ✓ | Thư mục chứa worker copies (tự tạo) |
| `swat_exe` | ✓ | Đường dẫn tới file SWAT.exe |
| `param_file` | — | File định nghĩa tham số `.txt` |
| `n_parallel` | — | Số worker song song (mặc định: 1) |

---

## Định dạng tham số bắt buộc

> **⚠️ Từ v0.2.1, tất cả key tham số phải dùng định dạng `name.ext`.**

Định dạng `name.ext` xác định rõ tên tham số và loại file SWAT cần cập nhật, tránh lỗi im lặng khi cùng tên tham số xuất hiện ở nhiều loại file.

```python
# ❌ Sai — tên trần không còn được chấp nhận
{"CN2": [(75.0, "v")]}

# ✅ Đúng — luôn kèm phần mở rộng file
{"CN2.mgt": [(75.0, "v")]}
```

Tham chiếu nhanh:

| Tham số | Key đúng | File SWAT |
|---------|----------|-----------|
| CN2 | `CN2.mgt` | `.mgt` (management) |
| ALPHA_BF | `ALPHA_BF.gw` | `.gw` (groundwater) |
| GW_DELAY | `GW_DELAY.gw` | `.gw` (groundwater) |
| ESCO | `ESCO.hru` | `.hru` (HRU) |
| SOL_AWC | `SOL_AWC.sol` | `.sol` (soil) |
| SURLAG | `SURLAG.bsn` | `.bsn` (basin) |

---

## Khởi động nhanh

```python
import pandas as pd
from spyswat import SWATProject
from spyswat.swat_calib.analysis import SWATCalibration

project = SWATProject(
    txinout_dir = "D:/SWAT/TxtInOut",
    working_dir = "D:/SWAT/workspace",
    swat_exe    = "D:/SWAT/swat.exe",
    n_parallel  = 8
)

obs = pd.read_csv("observed.csv", index_col="date", parse_dates=True)["flow"]

param_ranges = {
    "CN2.mgt":     (35.0, 98.0),
    "ALPHA_BF.gw": (0.0,  1.0),
    "GW_DELAY.gw": (30.0, 450.0),
    "ESCO.hru":    (0.01, 1.0),
    "SOL_AWC.sol": (0.01, 0.5),
}

calib = SWATCalibration(project)
calib.manager.setup_parallel(overwrite=True) #Set WorkingFolder truoc khi chay

# Quy trình đầy đủ: GLUE → best params → sensitivity → performance
result = calib.analyze(param_ranges, obs, n_samples=1000, threshold=0.5, seed=42)

print(f"Best NSE: {result['best_score']:.3f}")
print(result["sensitivity"])
print(result["performance"])
```

---

## Hiệu chỉnh

Từ v0.2.1, các thuật toán được tách thành lớp độc lập, truy cập qua `calib.glue`, `calib.de`, `calib.dds`, `calib.pso`.

### GLUE — Monte Carlo song song

```python
calib = SWATCalibration(project)

result = calib.glue.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    n_samples       = 1000,
    threshold       = 0.5,
    metric          = "nse",
    seed            = 42,
)

print(result["all_results"])        # DataFrame: tất cả 1000 lần chạy
print(result["behavioral_results"]) # DataFrame: chỉ các bộ behavioral (NSE ≥ 0.5)
print(f"Behavioral: {result['behavioral_ratio']:.1%}")
```

#### GLUE + 95PPU

```python
# Tính dải bất định 95PPU
unc = calib.glue.uncertainty_band(
    behavioral_df   = result["behavioral_results"],
    observed_series = obs,
    metric          = "nse",
)
print(f"p-factor: {unc['p_factor']:.3f}")   # ≥ 0.70 → tốt
print(f"r-factor: {unc['r_factor']:.3f}")   # ≤ 1.50 → tốt
unc["uncertainty_band"].plot()               # DataFrame: lower, upper, obs
```

### DDS — Dynamically Dimensioned Search

DDS tự điều chỉnh tỷ lệ perturbation theo tiến độ: `P = 1 - ln(i)/ln(N)`. Hiệu quả với ngân sách ≤ 500 lần chạy.

```python
result = calib.dds.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    n_iterations    = 300,
    r               = 0.2,
    seed            = 42,
    metric          = "nse",
)
print(f"Best NSE: {result['best_score']:.4f}")
print(result["best_params"])
print(result["history"])   # DataFrame: iteration, score
```

Dùng `DDS` standalone (không cần SWAT):

```python
from spyswat.swat_calib.analysis.algorithms import DDS

dds = DDS(
    param_ranges = param_ranges,
    objective    = my_objective_fn,   # callable: dict → float
    n_iterations = 300,
    seed         = 42,
    maximize     = True
)
result = dds.run()
```

### Parallel Differential Evolution

Mỗi thế hệ đánh giá toàn bộ population song song qua `run_batch`. Phù hợp khi có nhiều worker và budget lớn.

```python
result = calib.de.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    pop_size        = 20,
    max_generations = 40,
    F               = 0.8,
    CR              = 0.9,
    strategy        = "rand/1/bin",   # hoặc "best/1/bin"
    seed            = 42,
    tol             = 1e-6,
    patience        = 5,
)
print(f"Best NSE: {result['best_score']:.4f}")
print(result["history"])   # DataFrame: generation, best_score, mean_score
```

### PSO — Particle Swarm Optimization

Mỗi iteration đánh giá toàn bộ swarm song song qua `run_batch`. Trọng số inertia giảm tuyến tính `w_max → w_min` (Shi & Eberhart, 1998), tự cân bằng exploration / exploitation.

```python
result = calib.pso.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    n_particles     = 20,
    max_iterations  = 50,
    w_max           = 0.9,
    w_min           = 0.4,
    c1              = 2.0,
    c2              = 2.0,
    seed            = 42,
    tol             = 1e-6,
    patience        = 10,
)
print(f"Best NSE: {result['best_score']:.4f}")
print(result["best_params"])
print(result["history"])          # iteration, best_score, mean_score, std_score
print(result["all_evaluations"])  # vị trí tất cả hạt qua từng iteration
```

Dùng `PSO` standalone (không cần SWAT):

```python
from spyswat.swat_calib.analysis.algorithms import PSO

pso = PSO(
    param_ranges   = param_ranges,
    objective      = my_objective_fn,   # callable: dict → float
    n_particles    = 20,
    max_iterations = 100,
    seed           = 42,
    maximize       = True
)
result = pso.run()
```

### Scipy DE / Nelder-Mead (sequential)

```python
result = calib.optimize(
    param_ranges    = param_ranges,
    observed_series = obs,
    method          = "differential_evolution",  # hoặc "minimize"
    metric          = "nse",
    max_iter        = 100,
)
print(result["best_parameters"])
print(f"Best NSE: {result['best_objective_value']:.4f}")
```

### Định dạng param_ranges thống nhất

Từ v0.2.2, bounds, phương thức và danh sách subbasin có thể khai báo trong một dict duy nhất — không cần truyền riêng `param_methods` / `param_subbasins`. Tất cả định dạng đều backward-compatible và có thể kết hợp tự do.

```python
param_ranges = {
    # Định dạng cũ — chỉ có bounds (method mặc định = "v")
    "ESCO.hru":    (0.01, 1.0),

    # bounds + method
    "CN2.mgt":     ((35, 98),   "r"),

    # bounds + method + danh sách subbasin (tối ưu độc lập từng lưu vực)
    "ALPHA_BF.gw": ((0.0, 1.0), "r", [71, 45, 70]),
    "GW_DELAY.gw": ((0, 450),   "v", [12, 33]),
}

# Gọi như thường — không cần kwargs thêm
result = calib.glue.run(param_ranges, obs, n_samples=1000, seed=42)
result = calib.de.run(param_ranges, obs, pop_size=20, max_generations=40)
result = calib.dds.run(param_ranges, obs, n_iterations=300)
result = calib.pso.run(param_ranges, obs, n_particles=20, max_iterations=50)
result = calib.analyze(param_ranges, obs)
```

Mã phương thức:

| Code | Công thức | Khi nào dùng |
|------|-----------|-------------|
| `v` (mặc định) | `new = val` | Thay thế tuyệt đối |
| `r` | `new = old × (1 + val)` | Thay đổi tương đối |
| `a` | `new = old + val` | Cộng thêm |

Vẫn có thể truyền `param_methods` / `param_subbasins` như kwargs — chúng sẽ **override** giá trị trong spec:

```python
result = calib.glue.run(
    param_ranges    = param_ranges,
    observed_series = obs,
    param_methods   = {"CN2.mgt": "v"},       # override method trong spec
    param_subbasins = {"ESCO.hru": [5, 6, 7]}, # thêm subbasin cho ESCO
)
```

### Tối ưu độc lập cho từng lưu vực

Gán danh sách subbasin khác nhau cho từng tham số để hiệu chỉnh từng lưu vực một cách độc lập:

```python
param_ranges = {
    "CN2.mgt":     ((35, 98),   "r", [71, 45, 70]),   # lưu vực thượng nguồn
    "ALPHA_BF.gw": ((0.0, 1.0), "r", [71, 45, 70]),
    "GW_DELAY.gw": ((0, 450),   "v", [12, 33, 8]),    # lưu vực hạ nguồn
    "ESCO.hru":    (0.01, 1.0),                        # toàn lưu vực
}
result = calib.dds.run(param_ranges, obs, n_iterations=500)
print(result["best_params"])
# {"CN2.mgt": [(val, "r", [71,45,70])], "GW_DELAY.gw": [(val, "v", [12,33,8])], ...}
```

---

## Fig Viewer — Sơ đồ lưu vực tương tác

Trực quan hoá mạng lưới dẫn dòng SWAT (`fig.fig`) dưới dạng đồ thị SVG tương tác trong trình duyệt.

```python
# Qua SWATProject (đơn giản nhất)
project.fig_viewer(
    red_reaches  = [32, 33, 37, 38],   # tô đỏ các reach ID này
    output_path  = None,               # mặc định: TxtInOut/fig_viewer.html
    open_browser = False,              # True để tự mở trình duyệt
)
```

Standalone:

```python
from spyswat.swat_calib.visualization import FigViewer

viewer = FigViewer("duong/dan/TxtInOut")

# Chỉ phân tích (trả về dict)
data = viewer.parse(red_reaches=[32, 33])

# Tạo file HTML
path = viewer.build(
    red_reaches  = [32, 33, 37, 38],
    output_path  = "so_do_luuvuc.html",
    open_browser = False,
)
```

**Tính năng tương tác:**

| Tính năng | Mô tả |
|-----------|-------|
| Click node | Chọn và làm nổi bật các reach liên kết |
| Hover | Hiển thị chi tiết lệnh (ID, loại, tham số) |
| Nút/cạnh đỏ | Các reach trong `red_reaches` và các lệnh liên quan |
| Hào xanh | Làm nổi bật node được chọn |
| Cạnh nét đứt | Lệnh transfer |
| Cạnh xanh đậm | Cạnh đang hoạt động (hot edges) |
| Bảng Issues | Cảnh báo kiểm tra (ID trùng, tham chiếu sai, transfer không hợp lệ) |

## Kiểm định

```python
# Dùng best_params từ kết quả hiệu chỉnh
project.HRU.update_params(result["best_params"])
project.run()

sim = project.Output.read_rch(
    columns=["RCH", "MON", "FLOW_OUTcms"], reach_id=1
)["FLOW_OUTcms"]

obs_val = obs["2011-01-01":"2015-12-31"]
sim_val = sim["2011-01-01":"2015-12-31"]

stats  = project.Statistic.calculate_statistics(obs_val, sim_val)
rating = project.Statistic.evaluate_performance(obs_val, sim_val)
print(stats)   # {"nse": 0.71, "kge": 0.68, "r2": 0.75, ...}
print(rating)  # {"nse": "Good", ...}
```

Dùng `ValidationRunner` để tự động chia giai đoạn:

```python
from spyswat.swat_calib.calibration import ValidationRunner
from spyswat.swat_calib.calibration.validation_runner import PeriodConfig

runner = ValidationRunner(
    project, param_ranges, obs,
    PeriodConfig(
        calib_start = "2002-01-01",
        calib_end   = "2010-12-31",
        valid_start = "2011-01-01",
        valid_end   = "2015-12-31"
    )
)
r = runner.run(metric="nse", output_variable="FLOW_OUTcms")
print("Calib NSE:", r["calibration"]["nse"])
print("Valid NSE:", r["validation"]["nse"])
```

---

## Phân tích độ nhạy

### Từ kết quả GLUE (khuyến nghị — không tốn thêm lần chạy)

```python
sensitivity = project.Statistic.sensitivity_from_results(
    results_df  = result["all_results"],
    metric      = "nse",
    param_names = list(param_ranges.keys()),
    method      = "spearman",   # hoặc "prcc"
)
print(sensitivity)
# parameter      sensitivity_index  rank
# ALPHA_BF.gw         0.83           1
# CN2.mgt             0.61           2
# GW_DELAY.gw         0.45           3
```

### OAT — One-At-a-Time (song song)

```python
from spyswat.swat_calib.analysis import SWATSensitivity

sens = SWATSensitivity(project)
oat_df, indices = sens.one_at_a_time(
    param_ranges    = param_ranges,
    n_steps         = 10,
    observed_series = obs,
    metric          = "nse"
)
print(indices)
```

### Morris Method (song song)

```python
morris = sens.morris_method(
    param_ranges    = param_ranges,
    n_trajectories  = 10,
    observed_series = obs,
    metric          = "nse"
)
print(morris["morris_indices"])
```

---

## Đọc/ghi TxtInOut

### Cập nhật tham số

```python
project.HRU.update_params({
    "CN2.mgt":     [(75.0, "v")],
    "ALPHA_BF.gw": [(0.5,  "v")],
    "ESCO.hru":    [(0.1,  "r")],
    "SOL_AWC.sol": [(0.05, "a")],
})
```

### Cập nhật theo subbasin

```python
project.HRU.update_params({
    "CN2.mgt": [
        (75.0, "v", [1, 2, 3]),   # subbasins 1-3: gán 75
        (80.0, "v", [4, 5]),      # subbasins 4-5: gán 80
    ]
})
```

### Cập nhật từ DataFrame

```python
import pandas as pd

df = pd.DataFrame([
    {"param": "CN2.mgt",     "value": 75.0, "method": "v"},
    {"param": "ALPHA_BF.gw", "value": 0.5,  "method": "v"},
    {"param": "ESCO.hru",    "value": 0.1,  "method": "r"},
])
project.HRU.update_by_df(df)
```

### Đọc giá trị tham số hiện tại

```python
values = project.read_params_values(["CN2.mgt", "ALPHA_BF.gw", "ESCO.hru"])
```

---

## Đọc kết quả SWAT

```python
# output.rch
rch = project.Output.read_rch(
    columns  = ["RCH", "MON", "FLOW_OUTcms", "SED_OUTtons"],
    reach_id = 1
)

# output.hru
hru = project.Output.read_hru(
    columns = ["LULC", "HRU", "MON", "ET", "SURQ_GEN"]
)

# output.sub
sub = project.Output.read_sub(columns=["SUB", "MON", "PRECIP", "SURQ"])

# output.sed
sed = project.Output.read_sed()
```

Biến phổ biến trong output.rch:

| Biến | Đơn vị | Mô tả |
|------|--------|-------|
| `FLOW_OUTcms` | m³/s | Lưu lượng ra |
| `SED_OUTtons` | tấn | Bùn cát |
| `NO3_OUTkg` | kg | Nitrat |
| `ORG_N_kg` | kg | Nitơ hữu cơ |

---

## Thống kê hiệu suất

```python
stats  = project.Statistic.calculate_statistics(obs, sim,
    metrics=["nse", "kge", "r2", "rmse", "pbias", "rsr"])
rating = project.Statistic.evaluate_performance(obs, sim)
```

Thang đánh giá NSE (Moriasi et al., 2007):

| NSE | Đánh giá |
|-----|---------|
| > 0.75 | Very Good |
| 0.65–0.75 | Good |
| 0.50–0.65 | Satisfactory |
| 0.40–0.50 | Acceptable |
| ≤ 0.40 | Unsatisfactory |

---

## Chạy song song

SpySWAT dùng `ProcessPoolExecutor` với N bản sao TxtInOut, mỗi worker dùng bản sao riêng biệt.

```
1000 mẫu, 8 workers → 125 batch × T_swat ≈ tăng tốc 8×

Batch 1:   [s1  s2  s3  s4  s5  s6  s7  s8]  ← chạy đồng thời
Batch 2:   [s9  s10 s11 s12 s13 s14 s15 s16]
...
Batch 125: [s993..s1000]
```

Thiết lập thủ công:

```python
from spyswat.swat_calib.calibration import CalibrationManager

manager = CalibrationManager(project)
manager.setup_parallel(overwrite=True)


results = manager.run_batch(
    param_sets = [
        {"CN2.mgt": [(70.0, "v")]},
        {"CN2.mgt": [(75.0, "v")]},
        {"CN2.mgt": [(80.0, "v")]},
    ],
    observed    = obs,
    metrics     = ["nse"],
    reach_id    = 1,
)
print(results)   # DataFrame: nse
```

---

## API Reference

### SWATProject

```
project.HRU.update_params(param_dict)
project.HRU.update_by_df(df)
project.read_params_values(param_list)
project.run()
project.get_date_range(freq="D")
project.worker(index)
project.Output.read_rch / read_hru / read_sub / read_sed / read_watout
project.Statistic.calculate_statistics(obs, sim)
project.Statistic.evaluate_performance(obs, sim)
project.Statistic.sensitivity_from_results(df, metric, param_names, method)
project.FileCIO.get_date_range_sim(freq)
project.WorkingFolder.setup(overwrite)
project.info()
```


### SWATCalibration

```
calib = SWATCalibration(project)

# Thuật toán độc lập (ưu tiên dùng)  — param_ranges hỗ trợ định dạng thống nhất từ v0.2.2
calib.glue.run(param_ranges, obs, n_samples, threshold, metric, seed,
               param_methods, param_subbasins, ...) → dict
calib.glue.uncertainty_band(behavioral_df, obs, metric) → dict
calib.de.run(param_ranges, obs, pop_size, max_generations, F, CR, strategy,
             param_methods, param_subbasins, ...) → dict
calib.dds.run(param_ranges, obs, n_iterations, r, seed, metric,
              param_methods, param_subbasins, ...) → dict
calib.pso.run(param_ranges, obs, n_particles, max_iterations, w_max, w_min,
              c1, c2, v_max_ratio, seed, metric, tol, patience,
              param_methods, param_subbasins, ...) → dict

# Quy trình tổng hợp
calib.analyze(param_ranges, obs, n_samples, threshold, metric,
              sensitivity_method, seed, param_methods, param_subbasins) → dict
calib.optimize(param_ranges, obs, method, metric, max_iter,
               param_methods, param_subbasins) → dict

# Hạ tầng
calib.manager                          # CalibrationManager
calib.manager.run_iteration(param_dict, obs, metric,
                            methods=None, subbasins=None, ...)
    param_dict: {name: float}  (raw)  HOẶC  {name: [(val, method, ...)]}  (formatted)
calib.manager.run_batch(param_sets, obs, metrics,
                        methods=None, subbasins=None, ...)
calib.manager._parse_spec(param_ranges) → (bounds, methods, subbasins)
    Raises ValueError nếu old-format tuple có > 2 phần tử
calib.manager._format_params(raw_dict, methods=None, subbasins=None) → formatted_dict
calib.manager._align_series(obs, sim) → (obs_aligned, sim_aligned)
```

### Standalone Algorithms

```python
from spyswat.swat_calib.analysis.algorithms import DDS, DDSCalibration, GLUE, ParallelDE, PSO, PSOCalibration

# DDS thuần — không cần SWAT
DDS(param_ranges, objective_fn, n_iterations=200, r=0.2, seed=None, maximize=True)
  .run() → {"best_params", "best_score", "history"}

# DDSCalibration — wrapper cho SWAT
DDSCalibration(manager)
  .run(param_ranges, obs, n_iterations, r, seed, metric, ...) → dict

# GLUE standalone
GLUE(manager, analysis=None)
  .run(param_ranges, obs, n_samples, threshold, metric, seed, ...) → dict
  .uncertainty_band(behavioral_df, obs, metric, ...) → dict

# ParallelDE standalone
ParallelDE(manager)
  .run(param_ranges, obs, pop_size, max_generations, F, CR, strategy,
        param_methods, param_subbasins, ...) → dict

# PSO thuần — không cần SWAT
PSO(param_ranges, objective_fn, n_particles=None, max_iterations=100,
    w_max=0.9, w_min=0.4, c1=2.0, c2=2.0, seed=None, maximize=True)
  .run() → {"best_params", "best_score", "history"}

# PSOCalibration — wrapper cho SWAT
PSOCalibration(manager)
  .run(param_ranges, obs, n_particles, max_iterations, ...) → dict
```

### FigViewer

```python
from spyswat.swat_calib.visualization import FigViewer

FigViewer(txinout_dir)
  .parse(red_reaches=None) → dict
  .build(red_reaches=None, output_path=None, open_browser=True) → Path

# Qua SWATProject
project.fig_viewer(red_reaches=None, output_path=None, open_browser=True) → Path
```

---

## Cấu trúc thư mục

```
SpySWAT/
├── spyswat/
│   ├── swat_project.py               # SWATProject — điểm vào chính
│   └── swat_calib/
│       ├── core/       TxInOut, HRUManager, OutputFileManager, WorkingFolderManager
│       ├── io/         SWATParam, readers, writers, mapping_file, FileCIO
│       ├── calibration/ CalibrationManager (run_iteration, run_batch),
│       │               ValidationRunner
│       └── analysis/   SWATAnalysis (statistics), SWATCalibration (facade),
│                       SWATSensitivity
│                       └── algorithms/  dds.py, glue.py, parallel_de.py, pso.py
├── tests/              73 tests (pytest)
├── ARCHITECTURE.md     Kiến trúc chi tiết + sơ đồ kết nối
└── pyproject.toml
```

---

## Tests

```bash
pytest tests/ -v
# 73 passed in ~5s
```

---

## Tài liệu tham khảo

- Beven, K. & Binley, A. (1992). The future of distributed models. *Hydrological Processes*, 6(3), 279–298.
- Abbaspour, K.C. et al. (2007). Modelling hydrology and water quality. *Journal of Hydrology*, 333, 554–570.
- Tolson, B.A. & Shoemaker, C.A. (2007). Dynamically dimensioned search algorithm for computationally efficient watershed model calibration. *Water Resources Research*, 43(1), W01413.
- Storn, R. & Price, K. (1997). Differential evolution — a simple and efficient heuristic for global optimization. *Journal of Global Optimization*, 11(4), 341–359.
- Kennedy, J. & Eberhart, R. (1995). Particle swarm optimization. *Proc. ICNN'95*, 4, 1942–1948.
- Shi, Y. & Eberhart, R. (1998). A modified particle swarm optimizer. *Proc. IEEE ICEC*, 69–73.
- Moriasi, D.N. et al. (2007). Model evaluation guidelines for systematic quantification of accuracy in watershed simulations. *Trans. ASABE*, 50(3), 885–900.
- Helton, J.C. & Davis, F.J. (2003). Latin hypercube sampling and the propagation of uncertainty in analyses of complex systems. *Reliability Engineering & System Safety*, 81(1), 23–69.
