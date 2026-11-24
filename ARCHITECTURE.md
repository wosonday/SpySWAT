# SpySWAT — Kiến trúc và Hướng dẫn Kỹ thuật

> Phiên bản: 0.2.6 + các thay đổi chưa phát hành | Cập nhật: 2026-11-20
>
> Các mục mới: luồng chạy an toàn (2.3, 3.1, 3.2), ScenarioBatch (3.7), quyết định 5.6 và 5.8 → 5.13.

---

## 1. Tổng quan kiến trúc 3 tầng

SpySWAT được tổ chức theo **3 tầng** tách biệt rõ ràng:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TẦNG 1 — NGƯỜI DÙNG (USER LAYER)                  │
│                                                                       │
│  SWATProject   SWATCalibration   SWATSensitivity   ScenarioBatch    │
│      │                   │                        │         │        │
│      │          ┌────────┴────────┐               │         │        │
│      │          │  calib.glue     │               │         │        │
│      │          │  calib.de       │               │         │        │
│      │          │  calib.dds      │               │         │        │
│      │          │  calib.pso      │               │         │        │
│      │          │  calib.analyze()│               │         │        │
│      │          └────────┬────────┘               │         │        │
└──────┼───────────────────┼────────────────────────┼─────────┼────────┘
       │                   │                        │         │
┌──────▼───────────────────▼────────────────────────▼─────────▼────────┐
│                TẦNG 2 — HẠ TẦNG (INFRASTRUCTURE LAYER)               │
│                                                                       │
│     CalibrationManager                  WorkingFolderManager         │
│       run_iteration() / run_batch()       setup()                    │
│       record_run() → nhật ký CSV          run_parallel() → WorkerResult│
│     metric registry (statistics.py)                                   │
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
│   ├── .run_once(params, *, reach_id, output_variable,
│   │             methods=None, subbasins=None)        → Series
│   ├── .sandbox(names=None)                          → context manager
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
│         └── history              DataFrame (iteration, best_score)
│
├── .pso       → PSOCalibration(manager)
│   └── .run(param_ranges, obs, n_particles, max_iterations,
│             w_max, w_min, c1, c2, v_max_ratio, seed,
│             metric, output_variable, reach_id,
│             tol, patience, param_methods, param_subbasins) → dict
│         ├── best_params          dict
│         ├── best_score           float
│         ├── history              DataFrame (iteration, best/mean/std score)
│         └── all_evaluations      DataFrame
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

### 2.3 CalibrationManager — hạ tầng chạy tuần tự và song song

`calib_manager.py` điều phối chạy mô hình, backup/restore và căn chỉnh chuỗi.
Ba phần triển khai được tách riêng:

- `calibration/param_spec.py`: các hàm thuần `parse_spec`, `format_params`, `is_raw`,
  `param_columns`; manager giữ alias tĩnh và wrapper `_format_params` cho caller cũ.
- `calibration/run_log.py::RunLog(project)`: giữ trạng thái session, cột CSV, bộ đệm
  file khóa và cảnh báo; manager chuyển tiếp API log cũ sang `self._log`.
- `core/run_state.py`: `copy_over`, `rch_signature`, `stamp_output_rch`,
  `check_fresh_output_rch`, `StaleOutputError`. `workingFolder_manager.py` giữ các tên
  private cũ làm alias, kể cả cho worker được spawn trên Windows.

```
CalibrationManager(project)
│
├── _parse_spec(param_ranges)  [alias tĩnh tới param_spec.parse_spec]
│     Parse unified format → (bounds_dict, methods_dict, subbasins_dict)
│     Formats: (min, max) | ((min,max), method) | ((min,max), method, [subs])
│     Raises ValueError nếu old-format có > 2 phần tử
│
├── _format_params(raw_dict, methods=None, subbasins=None)
│     {name: float} → {name: [(val, method, [subs])]}
│     Wrapper tới param_spec.format_params; methods/subbasins là dict local
│
├── _log → RunLog(project)
│     Quản lý session, CSV, cảnh báo và bộ đệm; manager chỉ chuyển tiếp
│
├── run_once(params, *, reach_id=1, output_variable="FLOW_OUTcms",
│            methods=None, subbasins=None)
│     Format → update_params → stamp → SWAT → kiểm output mới → read_rch
│     Trả Series thô; không backup, không tính metric, không ghi log
│     Output không mới → StaleOutputError (lớp con RuntimeError)
│
├── sandbox(names=None)
│     Backup khi vào, restore trong finally; không chép/xóa output
│
├── _align_series(obs, sim)
│     freq = IPRINT trong file.cio ('MS' | 'D')  (không suy từ obs)
│     check_observation_step(obs.index, freq)  → ValueError nếu lệch ngày/tháng
│     Gán ngày mô phỏng cho sim (sai độ dài → ValueError), lấy giao với obs
│
├── _backup_state(names=None) / _restore_state()
│     Chỉ chép các file ĐẦU VÀO có thể bị sửa (không chép output, không xóa TxtInOut)
│     Backup chỉ bị xóa khi MỌI file đã chép lại thành công;
│     restore lỗi → giữ backup, lần _backup_state() sau hoàn tất nó trước
│
├── run_iteration(param_dict, obs, metric, reach_id, output_var,
│                methods=None, subbasins=None)
│   │
│   ├── 1. _format_params(param_dict, methods, subbasins)
│   ├── 2. _backup_state(names=formatted.keys())
│   ├── 3. run_once(formatted)   (ghi nghiêm ngặt, nguyên tử; kiểm output mới)
│   ├── 4. _align_series(obs, sim)
│   ├── 5. tính metric
│   ├── 6. _record_run(...) → RunLog → <session>_metrics.csv / _outputs.csv
│   └── 7. _restore_state()  (luôn chạy, kể cả khi lỗi hoặc Ctrl+C)
│
├── run_batch(param_sets, observed, metrics, reach_id, output_var,
│             methods=None, subbasins=None)
│   │
│   └── WorkingFolderManager.run_parallel() theo từng lô n_parallel
│         worker_i: khôi phục file gốc → áp p_i → SWAT → WorkerResult(ok, error)
│         ok=False → NaN cho mọi metric (không đọc output cũ)
│         → ghi nhật ký từng lần chạy → DataFrame(metrics)
│
└── record_run(params, scores, ...)   hook công khai cho GLUE.uncertainty_band,
                                      sensitivity và thuật toán tự viết
```

`run_iteration`, sensitivity, GLUE 95PPU và `ValidationRunner` đều gọi `run_once`,
không chép lại chuỗi chạy an toàn. Sensitivity/GLUE và validation có `restore=True`
dùng `sandbox()`. `run_iteration` giữ backup/restore tường minh để bảo toàn thông báo
kết hợp khi cả chạy mô hình và khôi phục cùng lỗi. Validation mặc định giữ tham số,
nên không vào sandbox khi `restore=False`.

Sensitivity và GLUE ghi log sau khi ra khỏi sandbox; khôi phục lỗi được ghi là lần
chạy thất bại. Các cột CSV, cách định dạng và API log công khai không đổi.

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
     └── writer: đọc latin-1, newline="" → sửa từng ô → tmp file → os.replace
         (giá trị rộng hơn ô / dòng ngắn → SWATFileFormatError, file không đổi)
     │
     ▼
SWATRun.run(TxtInOut/)   → SWAT.exe  (timeout, kill khi Ctrl+C, không kế thừa stdin)
     │
     ▼
OutputFileManager.read_rch(["FLOW_OUTcms"], reach_id=1)
     (cache theo (mtime_ns, size); bước in lấy từ IPRINT; file tháng tách theo khối)
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
    worker_1: khôi phục gốc → p1 → SWAT → NSE_1
    worker_2: khôi phục gốc → p2 → SWAT → NSE_2
    ...
    worker_8: khôi phục gốc → p8 → SWAT lỗi → WorkerResult(ok=False) → NaN
  Batch 2: p9..p16 → ...
  ...
  Batch 125: p993..p1000
     │
     ▼
DataFrame: 1000 hàng × (params + metrics); mỗi lô được ghi ngay vào nhật ký
```

Vì mỗi lần chạy bắt đầu từ bản gốc, thay đổi `r`/`a` ở lô 2 không cộng dồn lên lô 1. Hàm chạy trong worker (`prepare`, `extract`, `runner`) phải là hàm cấp module để pickle được; `setup()` / `run_parallel()` từ chối chạy bên trong tiến trình con (script thiếu `if __name__ == "__main__":`).

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

### 3.6 PSO — Particle Swarm Optimization

```
Iter 0: khởi tạo swarm P (n_particles × D) ngẫu nhiên trong bounds
        velocities V (n_particles × D) ngẫu nhiên trong [-v_max, v_max]
     │
     ▼
Đánh giá toàn bộ P qua run_batch (song song)
Ghi nhận pbest_i = P[i], gbest = argmax(scores)
     │
     ▼
Iter 1..max_iterations:
  w = w_max - (w_max - w_min) × t / max_iterations    # inertia decay
  For each particle i:
    V[i] = w × V[i]
           + c1 × r1 × (pbest_i - P[i])   # cognitive
           + c2 × r2 × (gbest  - P[i])    # social
    V[i] = clip(V[i], -v_max, v_max)
    P[i] = clip(P[i] + V[i], lower, upper)
  │
  ▼
  Đánh giá toàn bộ P qua run_batch
  Cập nhật pbest_i nếu score mới tốt hơn
  Cập nhật gbest nếu có cá thể mới tốt hơn
  │
  ▼
  Early stopping nếu |Δgbest| < tol trong "patience" iterations
```

*(Kennedy & Eberhart, 1995, ICNN; Shi & Eberhart, 1998, ICEC)*

### 3.7 ScenarioBatch — kịch bản × bộ tham số

```
scenarios = [S1 (TxtInOut riêng), S2 (weather_dir + cio), S3 (evaluate=False)]
param_sets = [P1, P2]           pairs=None → 6 việc (job_id = "S__P")
     │
     ▼
_plan()  → kiểm tên trùng, job_id trùng, pairs hợp lệ
_check_observation_steps()  → chỉ với kịch bản evaluate=True; lệch → ValueError trước khi chạy
signature (.signature.json)  → resume=True mà cấu hình đổi → ValueError
     │
     ▼
<working_dir>/_scenario_batch/TxInOut1..N   (tối đa n_parallel slot, không đụng worker của project)
  Một ProcessPoolExecutor(max_workers=n_parallel) cho cả lô; Scheduler (scenarios/scheduler.py)
  giữ hàng đợi việc theo thứ tự kế hoạch:
  - Slot rảnh nhận việc tiếp theo: ưu tiên việc cùng base TxtInOut hiện tại (không chép lại),
    nếu không có thì lấy việc đầu hàng đợi và reseed (xóa slot, copytree lại base trong worker)
  - _seed_and_run → _worker_job: chép overlays từ weather_dir, prepare=_prepare_dispatch
    (FileCIO.set(**cio)), chạy SWAT, extract=_extract_dispatch (bảng date × "{biến}@{reach}" → CSV,
    tính metric)
  - Lưu metrics.csv rồi summary.csv theo thứ tự kế hoạch sau mỗi n_parallel kết quả hoặc mỗi 10 s,
    và luôn lưu khi thoát (kể cả KeyboardInterrupt / ngoại lệ, rồi ném lại lỗi)
     │
     ▼
results_dir/
  series/<job_id>.csv      (ghi tmp → os.replace, thử lại khi file bị khóa)
  summary.csv              job_id, scenario, param_set, status, error, duration_s,
                           n_rows, series_file, evaluated, eval_note
  metrics.csv              job_id, scenario, param_set, variable, reach, metric, value
  (summary.csv bị khóa → ghi file có dấu thời gian + cảnh báo, không mất kết quả)
```

Việc lỗi không dừng lô (`status="failed"`): sau việc lỗi, slot được reseed trước việc kế tiếp (nếu thư mục slot bị khóa không xóa được thì thành `unusable`; nếu chép base lỗi thì các việc còn lại của base đó bị fail). `weather_dir` không đọc được hoặc pool bị gãy (`BrokenProcessPool`) đánh dấu `failed` cho các việc bị ảnh hưởng (giữ nguyên các kết quả hợp lệ đã hoàn thành) và `run()` vẫn trả về `BatchResult`; `resume=True` bỏ qua việc đã `ok` và còn file series để chạy lại phần còn lại. Kịch bản lịch sử không có ngày chung với thực đo được xử lý như `evaluate=False` (`eval_note` trong `summary.csv`).

---

## 4. Cấu trúc module

```
SpySWAT/
│
├── spyswat/
│   ├── __init__.py                    → export SWATProject
│   ├── __main__.py                    → CLI entry point (chạy SWAT một lần)
│   ├── logger.py                      → Logger, queue listener cho worker
│   ├── swat_project.py                → SWATProject (façade gốc; param_file tùy chọn)
│   │
│   └── swat_calib/
│       ├── __init__.py
│       │
│       ├── core/
│       │   ├── txinout.py             → TxInOut: quản lý đường dẫn
│       │   ├── hru_manager.py         → HRUManager: đọc/ghi tham số, validate_inputs()
│       │   ├── output_manager.py      → OutputFileManager: đọc output, cache theo dấu file
│       │   ├── run_state.py           → copy nguyên tử, kiểm output mới, StaleOutputError
│       │   └── workingFolder_manager.py → WorkingFolderManager, WorkerResult
│       │
│       ├── io/
│       │   ├── parameters.py          → SWATParam, SWATParamInfo
│       │   ├── readers.py             → fixed-width readers
│       │   ├── writers.py             → writer nghiêm ngặt, SWATFileFormatError
│       │   ├── mapping_file.py        → ánh xạ ext → file type
│       │   ├── mapping_output.py      → bố cục file output (rch, hru, sub, sed)
│       │   └── file_cio.py            → FileCIO: ngày mô phỏng, IPRINT, set()
│       │
│       ├── calibration/
│       │   ├── __init__.py
│       │   ├── calib_manager.py       → CalibrationManager, check_observation_step
│       │   ├── param_spec.py          → hàm thuần parse/format tham số và cột log
│       │   ├── run_log.py             → RunLog: session CSV, bộ đệm, cảnh báo
│       │   └── validation_runner.py   → ValidationRunner, PeriodConfig
│       │
│       ├── scenarios/
│       │   ├── model.py               → Scenario, ParamSet, Job, RunResult
│       │   └── batch.py               → ScenarioBatch, BatchResult
│       │
│       ├── run/run.py                 → SWATRun: tiến trình con, timeout
│       │
│       └── analysis/
│           ├── __init__.py
│           ├── statistics.py          → SWATAnalysis + METRIC_DIRECTIONS (bảng chỉ số)
│           ├── calibration.py         → SWATCalibration (facade, 159 lines)
│           ├── sensitivity.py         → SWATSensitivity
│           │
│           └── algorithms/
│               ├── __init__.py        → export DDS, DDSCalibration, GLUE, ParallelDE, PSO, PSOCalibration
│               ├── dds.py             → DDS (standalone) + DDSCalibration (wrapper)
│               ├── glue.py            → GLUE (standalone)
│               ├── parallel_de.py     → ParallelDE (standalone)
│               └── pso.py             → PSO (standalone) + PSOCalibration (wrapper)
│
├── tests/                     (347 test case; 336 passed, 11 skipped trên Windows, ~4–5 phút)
│   ├── test_calib_manager.py  run_iteration, run_batch, backup/restore, nhật ký
│   ├── test_run_once.py       run_once/sandbox, output cũ, caller dùng primitive chung
│   ├── test_calibration.py    facade + GLUE API
│   ├── test_dds.py / test_parallel_de.py
│   ├── test_inputs.py         writer nghiêm ngặt, FileCIO, validate_inputs
│   ├── test_outputs.py        read_rch theo IPRINT, cache, output.sed
│   ├── test_metrics.py        bảng chỉ số, NaN, on_failure
│   ├── test_statistics.py / test_sensitivity.py
│   ├── test_working_folder.py run_parallel, khôi phục gốc, prepare/extract
│   ├── test_scenarios.py      ScenarioBatch, resume, evaluate=False
│   ├── test_run.py            SWATRun, timeout, kill
│   └── test_project.py        SWATProject, __version__, CLI
│
├── docs/
│   ├── sample_run_*.py        ví dụ chạy đơn, song song, kịch bản
│   ├── SYSTEM_DESIGN_*.md     bản thiết kế/khảo sát gốc (lịch sử)
│   └── agents/                quy trình đội AI agent
├── .agents/                   sổ ghi chép theo đầu việc (xem AGENTS.md)
├── AGENTS.md / CLAUDE.md      hướng dẫn cho AI agent
├── README.md / README_VI.md
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

# Mới (standalone classes)
calib.glue.run(...)            # GLUE class độc lập
calib.de.run(...)              # ParallelDE class độc lập
calib.dds.run(...)             # DDSCalibration class độc lập
calib.pso.run(...)             # PSOCalibration class độc lập
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

Tầng User (GLUE, DE, DDS) không biết gì về xử lý song song — chúng chỉ gọi `run_batch()`.
`CalibrationManager` điều phối các lô; `WorkingFolderManager` giữ logic
`ProcessPoolExecutor` và worker. Điều này cho phép thay thế backend (ví dụ: Dask, Ray)
mà không ảnh hưởng các thuật toán.

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

### 5.6 Backup/restore an toàn (v0.2.5, siết lại ở phase 1)

`_backup_state()` kiểm tra nếu backup đang tồn tại thì gọi `_restore_state()` trước — tránh leak temp dir khi `run_iteration` bị gọi lại mà chưa restore. `_restore_state()` luôn chạy (kể cả khi lỗi hoặc Ctrl+C) để TxtInOut về trạng thái gốc.

Phase 1: backup chỉ chép các file đầu vào có thể bị sửa (không chép cả thư mục, không bao giờ xóa TxtInOut). Backup chỉ bị xóa khi mọi file đã được chép lại; nếu một file không chép được (ví dụ đang bị khóa), backup được giữ và đường dẫn được nêu trong `RuntimeError`.

ARCH-1: caller tuần tự dùng `run_once()` và bọc trong `sandbox(names=...)` khi cần
khôi phục. Primitive chỉ chạy và đọc kết quả; caller quyết định backup và ghi log.
`run_iteration()` giữ cặp backup/restore tường minh để không đổi lỗi kết hợp.
Các helper copy/kiểm output nằm ở `core/run_state.py`; alias private cũ vẫn được giữ.

### 5.7 Strict validation trong _parse_spec (v0.2.5)

Old format `(min, max)` với > 2 phần tử sẽ raise `ValueError` thay vì im lặng bỏ qua phần tử thừa. Điều này phát hiện sớm lỗi dùng nhầm format:

```python
# Raises ValueError rõ ràng
{"CN2.mgt": (35, 98, "r")}
# → ValueError: old format (min, max) accepts exactly 2 values, got 3.
#   Use new format: ((min, max), method, subbasins).
```

### 5.8 Báo lỗi thay vì trả số sai (phase 1)

Nguyên tắc chung của nhánh `fix/phase1-correctness`: một con số sai mà trông hợp lệ nguy hiểm hơn một lỗi. Vì vậy:

- Writer không còn điền `0.0` khi cắt sai vị trí; báo `SWATFileFormatError` và giữ nguyên file.
- Lần chạy SWAT không sinh output mới bị coi là lỗi (kiểm dấu `output.rch` trước/sau), không đọc output của lần trước.
- Thực đo và mô phỏng lệch bước (ngày/tháng) báo lỗi; SpySWAT không tự gộp.
- Khóa tham số không có trong file tham số báo lỗi trước khi sửa file hoặc khởi động worker.

### 5.9 Worker luôn bắt đầu từ bản gốc

Trước đây worker giữ trạng thái giữa các lô, nên `r`/`a` bị cộng dồn (lô 2 nhân lên kết quả của lô 1). Giờ `run_parallel()` chép lại các file đầu vào từ TxtInOut gốc trước mỗi việc. Chi phí: chép thêm vài file mỗi lần chạy; đổi lại kết quả không phụ thuộc thứ tự lô.

### 5.10 Một bảng chỉ số duy nhất

`METRIC_DIRECTIONS` trong `statistics.py` là nguồn duy nhất cho chiều tối ưu của mỗi chỉ số. Mọi thuật toán dùng `to_objective()` (luôn càng nhỏ càng tốt) và `best_index()` (an toàn với NaN). Lý do: trước đây mỗi thuật toán tự viết chiều tối ưu, và có chỗ coi `pbias` là "càng nhỏ càng tốt" theo giá trị có dấu (PBIAS âm lớn bị xem là tốt), thay vì theo `|pbias|`.

### 5.11 Lần chạy lỗi không bao giờ thành số liệu

NaN luôn xếp cuối khi chọn tốt nhất; lô toàn lỗi báo `RuntimeError`. Phân tích độ nhạy không thay NaN bằng giá trị giả: Morris bỏ quỹ đạo có lỗi, Sobol báo lỗi (giữ mẫu trong `last_samples`/`last_scores`), OAT loại lần lỗi. Thuật toán tuần tự cho người dùng chọn `on_failure="raise"` hoặc `"penalize"`.

### 5.12 Nhật ký lần chạy không bao giờ làm dừng hiệu chỉnh

Hiệu chỉnh có thể chạy nhiều giờ; mất kết quả vì lỗi ghi log là không chấp nhận được,
nhưng làm hỏng hiệu chỉnh vì log còn tệ hơn. `RunLog._record_run` bắt mọi exception và
chỉ cảnh báo một lần; file bị khóa thì giữ dòng trong bộ nhớ (tối đa 10 000 dòng mỗi
file) và ghi ở lần sau; file chỉ được tạo (O_EXCL) khi có dòng đầu tiên, nên không để
lại file rỗng. `CalibrationManager` chuyển tiếp `record_run`, `flush_log`,
`session_path`, `session_files`, `results_dir`, `log_outputs` và các helper tương thích
sang `RunLog`; cấu trúc cột và nội dung CSV được giữ nguyên. Sensitivity và GLUE ghi
sau khôi phục để phản ánh đúng cả lỗi restore. Quyết định này thay cho
"Decision 4: No persistence layer" trong `docs/SYSTEM_DESIGN_*.md`.

### 5.13 Mọi mã chạy song song phải pickle được

Windows dùng `spawn`: tiến trình con nạp lại script. Hàm truyền vào worker phải ở cấp module (không lambda, không closure); script phải nằm dưới `if __name__ == "__main__":`. Các hàm `setup()`, `run_parallel()`, `ScenarioBatch.run()` kiểm `multiprocessing.parent_process()` và báo lỗi rõ ràng thay vì sinh tiến trình đệ quy.

---

## 6. Quy tắc mở rộng

Thêm thuật toán mới (PSO đã có sẵn — xem `pso.py` làm mẫu):

```python
# 1. Tạo file mới
# spyswat/swat_calib/analysis/algorithms/myalgo.py
class MyAlgoCalibration:
    def __init__(self, manager):
        self._manager = manager

    def run(self, param_ranges, observed_series, ...) -> dict:
        bounds, _m, _s = self._manager._parse_spec(param_ranges)
        # Dùng self._manager.run_batch() để đánh giá song song
        ...
        return {
            "best_params": ...,   # bắt buộc
            "best_score":  ...,   # bắt buộc
            "history":     ...,   # bắt buộc (pd.DataFrame)
        }

# 2. Export từ __init__.py
from .myalgo import MyAlgoCalibration

# 3. Đăng ký trong SWATCalibration
self.myalgo = MyAlgoCalibration(self.manager)

# 4. Viết test
# tests/test_myalgo.py → mock manager.run_batch → test logic thuần
```

---

## 7. Tham chiếu nhanh

| Tình huống | Dùng |
|-----------|------|
| Khám phá (nhiều sample, song song) | `calib.glue.run(n_samples=1000)` |
| Tối ưu nhanh (budget nhỏ, <500) | `calib.dds.run(n_iterations=300)` |
| Tối ưu quần thể (swarm, song song) | `calib.pso.run(n_particles=20, max_iterations=50)` |
| Tối ưu chính xác (budget lớn) | `calib.de.run(pop_size=20, max_generations=40)` |
| Bất định 95PPU | `calib.glue.uncertainty_band(behavioral_df, obs)` |
| Quy trình đầy đủ 1 lần gọi | `calib.analyze(param_ranges, obs)` |
| Sensitivity không tốn thêm | `project.Statistic.sensitivity_from_results(all_results)` |
| Kiểm định tự động | `ValidationRunner(project, ..., PeriodConfig(...))` |
| Chạy 1 bộ tham số thủ công | `manager.run_iteration(param_dict, obs, "nse")` |
| Chạy N bộ song song thủ công | `manager.run_batch(param_sets, obs, ["nse"])` |
| Kịch bản × bộ tham số | `ScenarioBatch(project, results_dir).run(scenarios, param_sets, outputs=...)` |
| Ghi lần chạy của thuật toán tự viết | `manager.record_run(params, scores, sim=...)` |
| Kiểm file tham số khớp TxtInOut | `project.HRU.validate_inputs()` |
| Kiểm bước thời gian thực đo | `check_observation_step(obs.index, project.FileCIO.get_iprint())` |

---

## 8. Tài liệu tham khảo

- Beven, K. & Binley, A. (1992). The future of distributed models: model calibration and uncertainty prediction. *Hydrological Processes*, 6(3), 279–298.
- Abbaspour, K.C. et al. (2007). Modelling hydrology and water quality in the pre-alpine/alpine Thur watershed using SWAT. *Journal of Hydrology*, 333, 554–570.
- Tolson, B.A. & Shoemaker, C.A. (2007). Dynamically dimensioned search algorithm for computationally efficient watershed model calibration. *Water Resources Research*, 43(1), W01413.
- Storn, R. & Price, K. (1997). Differential evolution — a simple and efficient heuristic for global optimization over continuous spaces. *Journal of Global Optimization*, 11(4), 341–359.
- Kennedy, J. & Eberhart, R. (1995). Particle swarm optimization. *Proceedings of ICNN'95*, 4, 1942–1948.
- Shi, Y. & Eberhart, R. (1998). A modified particle swarm optimizer. *Proceedings of IEEE ICEC*, 69–73.
- Moriasi, D.N. et al. (2007). Model evaluation guidelines for systematic quantification of accuracy in watershed simulations. *Trans. ASABE*, 50(3), 885–900.
- Helton, J.C. & Davis, F.J. (2003). Latin hypercube sampling and the propagation of uncertainty in analyses of complex systems. *Reliability Engineering & System Safety*, 81(1), 23–69.
