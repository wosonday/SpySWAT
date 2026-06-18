# SpySWAT — Kiến trúc và Hướng dẫn Kỹ thuật

> Phiên bản: 0.2.5 | Cập nhật: 2026-06-18

---

## 1. Tổng quan kiến trúc 3 tầng

SpySWAT được tổ chức theo **3 tầng** tách biệt rõ ràng:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TẦNG 1 — NGƯỜI DÙNG (USER LAYER)                  │
│                                                                       │
│  SWATProject          SWATCalibration         SWATSensitivity        │
│      │                   │                        │                  │
│      │          ┌────────┴────────┐               │                  │
│      │          │  calib.glue     │               │                  │
│      │          │  calib.de       │               │                  │
│      │          │  calib.dds      │               │                  │
│      │          │  calib.analyze()│               │                  │
│      │          └────────┬────────┘               │                  │
└──────┼───────────────────┼────────────────────────┼──────────────────┘
       │                   │                        │
┌──────▼───────────────────▼────────────────────────▼──────────────────┐
│                TẦNG 2 — HẠ TẦNG (INFRASTRUCTURE LAYER)               │
│                                                                       │
│         CalibrationManager          WorkingFolderManager             │
│           run_iteration()                 setup()                    │
│           run_batch()                  n_parallel                    │
└──────────────────────────┬────────────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────────────┐
│                    TẦNG 3 — I/O & CORE                                 │
│                                                                        │
│  TxInOut · HRUManager · OutputFileManager · SWATRun · SWATParam       │
│  FileCIO · readers · writers · mapping_file                            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Sơ đồ kết nối chi tiết

### 2.1 SWATProject — điểm vào chính

```
SWATProject(txinout_dir, working_dir, swat_exe, param_file, n_parallel)
│
├── .txinout         → TxInOut
│   ├── directory                      (Path tới TxtInOut/)
│   ├── hru_info, number_hru, number_sub
│   ├── get_hru_file(ext, sub, hru)    → Path
│   ├── get_output_file(ext)           → Path
│   └── get_watershed_file(ext)        → Path
│
├── .HRU             → HRUManager
│   ├── update_params(param_dict)      {"CN2.mgt": [(75,"v")]}
│   ├── update_by_df(df)               DataFrame: param, value, method
│   └── read_muti_hru_param_values(lst) → dict
│
├── .Output          → OutputFileManager
│   ├── read_rch(columns, reach_id)    → DataFrame
│   ├── read_sub(columns, sub_id)      → DataFrame
│   ├── read_hru(columns, hru_id)      → DataFrame
│   ├── read_sed(columns, reach_id)    → DataFrame
│   └── read_watout(columns)           → DataFrame
│
├── .Statistic       → SWATAnalysis
│   ├── calculate_statistics(obs, sim, metrics)    → dict
│   ├── evaluate_performance(obs, sim)             → dict
│   └── sensitivity_from_results(df, metric, ...)  → DataFrame
│
├── .WorkingFolder   → WorkingFolderManager
│   ├── n_parallel
│   └── setup(overwrite)               → tạo worker dirs
│
├── .FileCIO         → FileCIO
│   └── get_date_range(freq)           → DatetimeIndex
│
├── .swat_exe        → SWATRun
│   └── run(directory)
│
└── .param_file      → SWATParam
    └── get(name_ext)                  → SWATParamInfo
```

### 2.2 SWATCalibration — Facade với Standalone Algorithms

```
SWATCalibration(project, analysis=None)
│
├── .manager   → CalibrationManager(project)
│   ├── .setup_parallel(overwrite)
│   ├── .run_iteration(param_dict, obs, metric, reach_id, output_var,
│   │                  methods=None, subbasins=None) → float
│   └── .run_batch(param_sets, observed, metrics, reach_id, output_var,
│                  methods=None, subbasins=None)      → DataFrame
│
├── .glue      → GLUE(manager, analysis)
│   ├── .run(param_ranges, obs, n_samples, threshold, metric, seed,
│   │         compute_uncertainty, param_methods, param_subbasins) → dict
│   │     ├── all_results          DataFrame (n_samples × params+metric)
│   │     ├── behavioral_results   DataFrame (subset ≥ threshold)
│   │     └── behavioral_ratio     float
│   └── .uncertainty_band(behavioral_df, obs, metric) → dict
│         ├── uncertainty_band     DataFrame (lower, upper, obs)
│         ├── p_factor             float (≥ 0.70 → tốt)
│         └── r_factor             float (≤ 1.50 → tốt)
│
├── .de        → ParallelDE(manager)
│   └── .run(param_ranges, obs, pop_size, max_generations, F, CR,
│             strategy, seed, tol, patience,
│             param_methods, param_subbasins) → dict
│         ├── best_params          dict
│         ├── best_score           float
│         ├── history              DataFrame (generation, best/mean/std score)
│         └── all_evaluations      DataFrame
│
├── .dds       → DDSCalibration(manager)
│   └── .run(param_ranges, obs, n_iterations, r, seed,
│             metric, output_variable, reach_id, maximize,
│             param_methods, param_subbasins) → dict
│         ├── best_params          dict
│         ├── best_score           float
│         └── history              DataFrame
│
├── .analyze(param_ranges, obs, n_samples, threshold, metric,
│            sensitivity_method, seed,
│            param_methods, param_subbasins) → dict
│   [GLUE → best params → sensitivity → performance]
│   ├── best_params, best_score
│   ├── all_results, behavioral_results, behavioral_ratio
│   ├── sensitivity              DataFrame
│   └── performance              dict
│
└── .optimize(param_ranges, obs, method, metric, max_iter,
              param_methods, param_subbasins) → dict
    [scipy DE / minimize — single-threaded]
    ├── best_parameters
    ├── best_objective_value
    ├── history
    └── scipy_result
```

### 2.3 CalibrationManager — hạ tầng song song

```
CalibrationManager(project)
│
├── _parse_spec(param_ranges)  [staticmethod]
│     Parse unified format → (bounds_dict, methods_dict, subbasins_dict)
│     Formats: (min, max) | ((min,max), method) | ((min,max), method, [subs])
│     Raises ValueError nếu old-format có > 2 phần tử
│
├── _format_params(raw_dict, methods=None, subbasins=None)
│     {name: float} → {name: [(val, method, [subs])]}
│     methods/subbasins là dict local — không có shared state
│
├── _align_series(obs, sim)
│     pd.infer_freq(obs.index) → 'MS' hoặc 'D'
│     Gán DatetimeIndex cho sim, lấy giao với obs
│
├── _backup_state() / _restore_state()
│     Tạo tmp dir → copytree TxtInOut vào backup
│     Nếu backup tồn tại → restore trước khi tạo mới (không leak)
│
├── run_iteration(param_dict, obs, metric, reach_id, output_var,
│                methods=None, subbasins=None)
│   │
│   ├── 1. _backup_state()
│   ├── 2. _format_params(param_dict, methods, subbasins)
│   ├── 3. project.HRU.update_params(formatted)
│   ├── 4. project.run()
│   ├── 5. project.Output.read_rch(...)
│   ├── 6. _align_series(obs, sim)
│   ├── 7. calculate metric → return float
│   └── 8. finally: _restore_state()  (luôn khôi phục)
│
└── run_batch(param_sets, observed, metrics, reach_id, output_var,
              methods=None, subbasins=None)
    │
    └── ProcessPoolExecutor(n_parallel)
          worker_1: formatted_p1 → SWAT → _align_series → metrics
          worker_2: formatted_p2 → SWAT → _align_series → metrics
          ...
          worker_N: formatted_pN → SWAT → _align_series → metrics
          → DataFrame(metrics)
```

---

## 3. Luồng dữ liệu

### 3.1 Sequential — 1 lần chạy

```
param_dict {"CN2.mgt": [(75,"v")], "ALPHA_BF.gw": [(0.5,"v")]}
     │
     ▼
HRUManager.update_params()
     │
     ├── SWATParam.get("CN2.mgt")      → line=8, col=3..12
     ├── SWATParam.get("ALPHA_BF.gw")  → line=6, col=3..12
     └── HRUWriter.write_column(...)   → ghi fixed-width vào file
     │
     ▼
SWATRun.run(TxtInOut/)   → SWAT.exe
     │
     ▼
OutputFileManager.read_rch(["FLOW_OUTcms"], reach_id=1)
     │
     ▼
SWATAnalysis.calculate_statistics(obs, sim)
     │
     ▼
NSE = 0.78
```

### 3.2 Parallel — run_batch (N workers)

```
param_sets = [p1, p2, ..., p1000]          n_parallel = 8
     │
     ▼
WorkingFolderManager.setup()
  → worker_1/TxtInOut/  (bản sao)
  → worker_2/TxtInOut/
  → ...
  → worker_8/TxtInOut/
     │
     ▼
ProcessPoolExecutor(8)
  Batch 1 (8 workers, đồng thời):
    worker_1: p1 → SWAT → NSE_1
    worker_2: p2 → SWAT → NSE_2
    ...
    worker_8: p8 → SWAT → NSE_8
  Batch 2: p9..p16 → ...
  ...
  Batch 125: p993..p1000
     │
     ▼
DataFrame: 1000 hàng × (params + metrics)
```

### 3.3 GLUE → 95PPU

```
n_samples LHS samples (seeded)
     │
     ▼
run_batch (parallel)
     │
     ▼
all_results DataFrame
     │
     ├─ [NSE ≥ threshold] → behavioral_results
     │                           │
     │                           ▼
     │                  uncertainty_band()
     │                    weight_i = NSE_i / ΣNSEj
     │                    sim_i chạy lại với best params
     │                    lower_95 = weighted CDF 2.5%
     │                    upper_95 = weighted CDF 97.5%
     │                    p_factor = % obs nằm trong [lower, upper]
     │                    r_factor = mean(upper-lower) / std(obs)
     │
     └─ sensitivity_from_results(Spearman/PRCC, 0 extra runs)
```

### 3.4 DDS — Dynamically Dimensioned Search

```
i = 1..N
     │
     ▼
P_perturb = 1 - ln(i) / ln(N)    # giảm dần theo tiến độ
     │
     ▼
Chọn ngẫu nhiên d tham số để perturb (d ~ Binomial(D, P_perturb))
     │
     ▼
x_new[j] = x_best[j] + r × N(0,1) × (max_j - min_j)
           phản chiếu tại biên nếu vượt bounds
     │
     ▼
f(x_new) > f(x_best) ?
    Yes → x_best = x_new
    No  → giữ x_best
```

*(Tolson & Shoemaker, 2007, Water Resources Research)*

### 3.5 Parallel DE — Differential Evolution

```
Gen 0: khởi tạo population P (pop_size × D) ngẫu nhiên
     │
     ▼
Đánh giá toàn bộ P qua run_batch (song song)
     │
     ▼
Gen 1..max_generations:
  For each i in [0, pop_size):
    strategy "rand/1/bin":
      a, b, c = 3 cá thể ngẫu nhiên ≠ i
      mutant = a + F × (b - c)   (clip về bounds)
      trial = crossover(P[i], mutant, CR)
  │
  ▼
  Đánh giá toàn bộ trial_population qua run_batch
  │
  ▼
  Selection: P[i] = trial[i] nếu score tốt hơn
  │
  ▼
  Early stopping nếu |Δbest| < tol trong "patience" generations
```

*(Storn & Price, 1997, Journal of Global Optimization)*

---

## 4. Cấu trúc module

```
SpySWAT/
│
├── spyswat/
│   ├── __init__.py                    → export SWATProject
│   ├── __main__.py                    → CLI entry point
│   ├── swat_project.py                → SWATProject (façade gốc)
│   │
│   └── swat_calib/
│       ├── __init__.py
│       │
│       ├── core/
│       │   ├── txinout.py             → TxInOut: quản lý đường dẫn
│       │   ├── hru_manager.py         → HRUManager: đọc/ghi tham số
│       │   ├── output_manager.py      → OutputFileManager: đọc output
│       │   └── workingFolder_manager.py → WorkingFolderManager: worker dirs
│       │
│       ├── io/
│       │   ├── parameters.py          → SWATParam, SWATParamInfo
│       │   ├── readers.py             → fixed-width readers
│       │   ├── writers.py             → HRUWriter: column-based write
│       │   ├── mapping_file.py        → ánh xạ ext → file type
│       │   └── file_cio.py            → FileCIO: đọc file.cio
│       │
│       ├── calibration/
│       │   ├── __init__.py
│       │   ├── calib_manager.py       → CalibrationManager
│       │   └── validation_runner.py   → ValidationRunner, PeriodConfig
│       │
│       └── analysis/
│           ├── __init__.py
│           ├── statistics.py          → SWATAnalysis
│           ├── calibration.py         → SWATCalibration (facade, 159 lines)
│           ├── sensitivity.py         → SWATSensitivity
│           │
│           └── algorithms/
│               ├── __init__.py        → export DDS, DDSCalibration, GLUE, ParallelDE
│               ├── dds.py             → DDS (standalone) + DDSCalibration (wrapper)
│               ├── glue.py            → GLUE (standalone)
│               └── parallel_de.py     → ParallelDE (standalone)
│
├── tests/
│   ├── test_calibration.py    (18 tests — facade + GLUE API)
│   ├── test_calib_manager.py  (12 tests — run_iteration, run_batch)
│   ├── test_dds.py            (18 tests — DDS algorithm)
│   ├── test_parallel_de.py    (15 tests — ParallelDE)
│   ├── test_glue.py           (10 tests — GLUE + 95PPU)
│   └── ...
│           73 tests total, ~5s
│
├── README_VI.md
├── README_EN.md
├── ARCHITECTURE.md            (file này)
├── CHANGELOG.md
└── pyproject.toml
```

---

## 5. Quyết định thiết kế quan trọng

### 5.1 Standalone + Facade pattern

Trước v0.2.1, `SWATCalibration` chứa toàn bộ logic GLUE, DE, DDS như các method trực tiếp — dẫn đến class 297 dòng khó test và mở rộng.

Từ v0.2.1:

```
# Cũ (297 dòng, mọi thứ trong 1 class)
calib.glue_analysis(...)       # delegate → bị xóa
calib.parallel_de(...)         # delegate → bị xóa
calib.dds_analysis(...)        # delegate → bị xóa

# Mới (159 dòng, standalone classes)
calib.glue.run(...)            # GLUE class độc lập
calib.de.run(...)              # ParallelDE class độc lập
calib.dds.run(...)             # DDSCalibration class độc lập
```

Lợi ích:
- Mỗi class có thể test độc lập với mock manager
- Dùng được không qua `SWATCalibration` nếu muốn
- `SWATCalibration` chỉ còn `optimize()` và `analyze()` — dễ đọc

### 5.2 name.ext format cho tham số

Cùng tên `CN2` có thể xuất hiện trong nhiều loại file SWAT. Dùng `CN2.mgt` thay vì `CN2` giúp:
- Không cần tìm kiếm file → tra cứu O(1) qua `SWATParam`
- Lỗi rõ ràng ngay khi gọi, không im lặng ghi sai file

### 5.3 CalibrationManager là ranh giới song song

Tầng User (GLUE, DE, DDS) không biết gì về xử lý song song — chúng chỉ gọi `run_batch()`. Mọi logic ProcessPoolExecutor nằm trong `CalibrationManager`. Điều này cho phép thay thế backend (ví dụ: Dask, Ray) mà không ảnh hưởng các thuật toán.

### 5.4 Sensitivity không tốn thêm lần chạy SWAT

`sensitivity_from_results()` dùng Spearman/PRCC trực tiếp trên DataFrame kết quả GLUE — không cần chạy thêm lần nào. Đây là cách tiếp cận tiêu chuẩn trong hiệu chỉnh Bayesian (Beven & Binley, 1992).

### 5.5 Không có shared mutable state (v0.2.5)

Trước v0.2.5, `CalibrationManager.__init__` lưu `self._methods` và `self._subbasins` — gây race condition khi `run_batch` chạy song song nhiều thuật toán cùng lúc.

Từ v0.2.5: `methods` và `subbasins` là tham số cục bộ, truyền qua call chain `run_iteration → _format_params`. Không còn shared state; các thuật toán standalone (GLUE, DE, DDS) tự parse `param_ranges` và truyền locals xuống manager.

```python
# ❌ Cũ — shared state, race condition
self.manager._methods  = methods
self.manager._subbasins = subbasins

# ✅ Mới — local args
score = self.manager.run_iteration(..., methods=methods, subbasins=subbasins)
```

### 5.6 Backup/restore an toàn (v0.2.5)

`_backup_state()` kiểm tra nếu backup đang tồn tại thì gọi `_restore_state()` trước — tránh leak temp dir khi `run_iteration` bị gọi lại mà chưa restore. `_restore_state()` luôn được gọi trong `finally` để đảm bảo TxtInOut về trạng thái gốc dù có exception.

### 5.7 Strict validation trong _parse_spec (v0.2.5)

Old format `(min, max)` với > 2 phần tử sẽ raise `ValueError` thay vì im lặng bỏ qua phần tử thừa. Điều này phát hiện sớm lỗi dùng nhầm format:

```python
# Raises ValueError rõ ràng
{"CN2.mgt": (35, 98, "r")}
# → ValueError: old format (min, max) accepts exactly 2 values, got 3.
#   Use new format: ((min, max), method, subbasins).
```

---

## 6. Quy tắc mở rộng

Thêm thuật toán mới (ví dụ: PSO):

```python
# 1. Tạo file mới
# spyswat/swat_calib/analysis/algorithms/pso.py
class PSO:
    def __init__(self, manager):
        self._manager = manager

    def run(self, param_ranges, observed_series, ...) -> dict:
        # Dùng self._manager.run_batch() cho mỗi swarm evaluation
        ...

# 2. Export từ __init__.py
# algorithms/__init__.py
from .pso import PSO

# 3. Đăng ký trong SWATCalibration
# analysis/calibration.py
self.pso = PSO(self.manager)

# 4. Viết test
# tests/test_pso.py
# mock manager.run_batch → test logic thuần
```

---

## 7. Tham chiếu nhanh

| Tình huống | Dùng |
|-----------|------|
| Khám phá (nhiều sample, song song) | `calib.glue.run(n_samples=1000)` |
| Tối ưu nhanh (budget nhỏ, <500) | `calib.dds.run(n_iterations=300)` |
| Tối ưu chính xác (budget lớn) | `calib.de.run(pop_size=20, max_generations=40)` |
| Bất định 95PPU | `calib.glue.uncertainty_band(behavioral_df, obs)` |
| Quy trình đầy đủ 1 lần gọi | `calib.analyze(param_ranges, obs)` |
| Sensitivity không tốn thêm | `project.Statistic.sensitivity_from_results(all_results)` |
| Kiểm định tự động | `ValidationRunner(project, ..., PeriodConfig(...))` |
| Chạy 1 bộ tham số thủ công | `manager.run_iteration(param_dict, obs, "nse")` |
| Chạy N bộ song song thủ công | `manager.run_batch(param_sets, obs, ["nse"])` |

---

## 8. Tài liệu tham khảo

- Beven, K. & Binley, A. (1992). The future of distributed models: model calibration and uncertainty prediction. *Hydrological Processes*, 6(3), 279–298.
- Abbaspour, K.C. et al. (2007). Modelling hydrology and water quality in the pre-alpine/alpine Thur watershed using SWAT. *Journal of Hydrology*, 333, 554–570.
- Tolson, B.A. & Shoemaker, C.A. (2007). Dynamically dimensioned search algorithm for computationally efficient watershed model calibration. *Water Resources Research*, 43(1), W01413.
- Storn, R. & Price, K. (1997). Differential evolution — a simple and efficient heuristic for global optimization over continuous spaces. *Journal of Global Optimization*, 11(4), 341–359.
- Moriasi, D.N. et al. (2007). Model evaluation guidelines for systematic quantification of accuracy in watershed simulations. *Trans. ASABE*, 50(3), 885–900.
- Helton, J.C. & Davis, F.J. (2003). Latin hypercube sampling and the propagation of uncertainty in analyses of complex systems. *Reliability Engineering & System Safety*, 81(1), 23–69.
