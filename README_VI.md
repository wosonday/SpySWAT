# SpySWAT 🌊

**Thư viện Python cho hiệu chỉnh, kiểm định và phân tích độ nhạy mô hình SWAT**

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-464%20passed-brightgreen)]()
[![Version](https://img.shields.io/badge/version-0.3.0-orange)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

> English version: [README.md](README.md) · Kiến trúc chi tiết: [ARCHITECTURE.md](ARCHITECTURE.md) · Lịch sử: [CHANGELOG.md](CHANGELOG.md) · Làm việc với AI agent: [AGENTS.md](AGENTS.md), [AGENTS-TUTORIAL.md](AGENTS-TUTORIAL.md)

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Cài đặt](#cài-đặt)
- [Thiết lập dự án](#thiết-lập-dự-án)
- [Định dạng tham số bắt buộc](#định-dạng-tham-số-bắt-buộc)
- [Khởi động nhanh](#khởi-động-nhanh)
- [Hiệu chỉnh](#hiệu-chỉnh)
- [Hiệu chỉnh đa trạm](#hiệu-chỉnh-đa-trạm)
- [Fig Viewer](#fig-viewer--sơ-đồ-lưu-vực-tương-tác)
- [Đánh giá theo giai đoạn](#đánh-giá-theo-giai-đoạn)
- [Thư mục phiên chạy & Nhật ký lần chạy](#thư-mục-phiên-chạy--nhật-ký-lần-chạy)
- [Chạy theo kịch bản](#chạy-theo-kịch-bản)
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
- **Chạy theo kịch bản**: kịch bản sử dụng đất / khí hậu × bộ tham số, song song, chạy tiếp được
- **Nhật ký lần chạy**: chỉ số và chuỗi mô phỏng của mỗi lần chạy được ghi nối vào CSV ngay khi chạy xong
- Báo lỗi rõ ràng: tệp sai định dạng, lệch bước thời gian, lần chạy SWAT lỗi đều báo lỗi hoặc cho điểm NaN; không âm thầm điền `0.0`

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
| `param_file` | — | File định nghĩa tham số `.txt` (chỉ cần khi sửa tham số: `project.HRU`, `read_params_values`) |
| `n_parallel` | — | Số worker song song (mặc định: 1) |

> **Windows:** chạy song song sẽ sinh tiến trình mới và nạp lại script của bạn. Đặt mã của script dưới `if __name__ == "__main__":` (xem `docs/sample_run_*.py`); nếu không SpySWAT sẽ báo lỗi rõ ràng.

Kiểm tra file tham số có khớp với TxtInOut trước khi hiệu chỉnh:

```python
problems = project.HRU.validate_inputs()   # DataFrame rỗng = mọi vị trí đều hợp lệ
```

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

Từ **0.3.0**, quy trình hằng ngày chạy qua facade trên `SWATProject` (`calibration`, `evaluate`, `sensitivity`, `scenarios`, `apply`) với một bộ từ vựng thống nhất:

```python
import pandas as pd
from spyswat import SWATProject
from spyswat.swat_calib.scenarios import Scenario

if __name__ == "__main__":
    project = SWATProject(
        txinout_dir = "D:/SWAT/TxtInOut",
        working_dir = "D:/SWAT/workspace",
        swat_exe    = "D:/SWAT/swat_rev688.exe",
        param_file  = "D:/SWAT/params.txt",
        n_parallel  = 8,
    )

    obs = pd.read_csv("D:/SWAT/observed.csv", index_col="date", parse_dates=True)["flow"]

    param_ranges = {
        "CN2.mgt":     ((-0.2, 0.2), "r"),
        "ALPHA_BF.gw": (0.0,  1.0),
        "GW_DELAY.gw": (30.0, 450.0),
        "ESCO.hru":    (0.01, 1.0),
        "SOL_AWC.sol": ((-0.25, 0.25), "r"),
    }

    # 1. Hiệu chỉnh trên calib_period và chấm điểm cả valid_period trong cùng một lần chạy
    res = project.calibration(
        param_ranges,
        observed     = {("FLOW_OUTcms", 1): obs},
        calib_period = ("2005-01-01", "2010-12-31"),
        valid_period = ("2011-01-01", "2015-12-31"),
        algorithm    = "glue",
        n_samples    = 500,
        seed         = 42,
    )

    print(res.metrics)       # chỉ số bộ tốt nhất cho calib & valid
    print(res.sensitivity)   # độ nhạy hồi quy OLS (0 lần chạy SWAT thêm)

    # 2. Tự kiểm tra lại chuỗi mô phỏng bằng chính hàm evaluate()
    sim_best = res.series("FLOW_OUTcms", 1)[f"run_{res.best_run_id}"]
    ev = project.evaluate(
        {("FLOW_OUTcms", 1): sim_best},
        {("FLOW_OUTcms", 1): obs},
        periods={"calib": ("2005-01-01", "2010-12-31"),
                 "valid": ("2011-01-01", "2015-12-31")},
    )
    print(ev.table)

    # 3. Đưa thẳng 10 bộ tham số tốt nhất vào chạy kịch bản
    scen_res = project.scenarios(
        [Scenario("LUC2020", txinout_dir="D:/SWAT/LUC2020/TxtInOut")],
        res.top(10),
        outputs={"FLOW_OUTcms": [1]},
        observed={("FLOW_OUTcms", 1): obs},
    )
    print(scen_res.summary)
```

---

## Hiệu chỉnh

Điểm vào khuyến nghị là `project.calibration(...)`:

```python
res = project.calibration(
    param_ranges,
    observed,
    calib_period = ("2005-01-01", "2010-12-31"),
    valid_period = ("2011-01-01", "2015-12-31"),
    algorithm    = "glue",                       # "glue" | "pso" | "de" | "dds"
    metric       = "nse",
    metrics      = ("nse", "kge", "pbias", "r2"),
    weights      = None,
    outputs      = None,
    step         = None,                         # None | "M"
    agg          = None,                         # {variable: "mean" | "sum"}
    n_parallel   = None,                         # mặc định lấy theo n_parallel của project
    seed         = 42,
    results_dir  = None,                         # mặc định <working_dir>/calibration_results
    session      = None,                         # tự đặt tên <YYYYMMDD_HHMMSS>_<algorithm>_<metric>
    resume       = True,
    sensitivity  = True,
    # ...cộng thêm tùy chọn riêng của thuật toán như n_samples=500, threshold=0.5
)
```

Mỗi lần đánh giá chạy toàn bộ giai đoạn mô phỏng trong `file.cio` một lần; `calib_period` dùng cho hàm mục tiêu (`score`), đồng thời cả hai giai đoạn `calib_period` và `valid_period` đều được tính và lưu cho mọi lần chạy. Thư mục `TxtInOut` gốc không bao giờ bị sửa trong quá trình hiệu chỉnh.

> **Chạy tiếp bằng replay (`resume=True`):** để tiếp tục một lần hiệu chỉnh bị gián
> đoạn hoặc đã xong, gọi lại `project.calibration(...)` với cùng tên `session=` và
> `resume=True` (mặc định). Các lần chạy đã ghi nhận được phát lại từ thư mục phiên —
> SWAT không bao giờ chạy lại chúng — và chỉ những lần đánh giá còn lại mới chạy.
> Cấu hình phải khớp với phiên đã lưu: cùng `param_ranges` (khóa, thứ tự và cận),
> `observed`, `metric`/`metrics`, tùy chọn thuật toán và `seed` (truyền `seed=None`
> để dùng lại seed đã lưu); nếu không sẽ ném `ValueError` và phiên được giữ nguyên.
> Phiên không tồn tại ném `FileNotFoundError`; `resume=False` trên phiên đã tồn tại
> ném `FileExistsError`.

`project.calibration(...)` trả về `CalibrationResult`:

| Thuộc tính / Phương thức | Mô tả |
|---|---|
| `res.best_params`, `res.best_score`, `res.best_run_id` | Bộ tham số tốt nhất (`{name: [(val, method, [subs])]}`), `score` tốt nhất và `run_id` |
| `res.runs` | DataFrame tất cả các lần chạy (`run_id`, `time`, `status`, `error`, `is_initial`, tham số, `score`) |
| `res.metrics` | `EvaluationResult.table` của lần chạy tốt nhất trên `calib` và `valid` |
| `res.sensitivity`, `res.sensitivity_status` | Bảng độ nhạy hồi quy OLS (và trạng thái, vd `"ok"` hoặc `"insufficient runs"`) |
| `res.session_dir` | Đường dẫn tới thư mục phiên chạy |
| `res.top(n)` | `n` bộ tham số tốt nhất (bỏ lần lỗi) dạng `ParamSet` tên `run_<id>` |
| `res.select(**conditions)` | Lọc các lần chạy thành `ParamSet`, vd `select(nse__gt=0.5, site=("FLOW_OUTcms", 1), period="calib", how="all")` (`gt`/`gte`/`lt`/`lte`) |
| `res.best_param_set()` | Bộ tốt nhất dạng `ParamSet` |
| `res.series(variable, reach)` | Đọc chậm (lazy) chuỗi mô phỏng đã lưu (`date` × `run_<id>`) |
| `res.site_metrics(variable, reach)` | Đọc chậm các dòng chỉ số theo từng trạm (`run_id`, `<metric>_<period>`) |
| `CalibrationResult.load(session_dir)` | Mở lại một phiên chạy đã lưu (metadata đọc ngay, chuỗi đọc chậm) |

Truy cập kiểu dict (`res["best_params"]`, `res["best_score"]`, `res["history"]`) vẫn được giữ để tương thích ngược.

### Các lớp thuật toán cấp thấp (`SWATCalibration`)

Bạn vẫn có thể gọi trực tiếp các lớp thuật toán qua `SWATCalibration(project)` (`calib.glue`, `calib.de`, `calib.dds`, `calib.pso`). Các tham số cũ (`observed_series`, `reach_id`, `output_variable`) vẫn hoạt động kèm `DeprecationWarning` cho tới **0.4.0**; code mới nên dùng `observed` và `outputs`.

### GLUE — Monte Carlo song song

```python
from spyswat.swat_calib.analysis import SWATCalibration

calib = SWATCalibration(project)
calib.manager.setup_parallel(overwrite=True)

result = calib.glue.run(
    param_ranges = param_ranges,
    observed     = obs,
    n_samples    = 1000,
    threshold    = 0.5,
    metric       = "nse",
    outputs      = {"FLOW_OUTcms": [1]},
    seed         = 42,
)

print(result["all_results"])        # DataFrame: tất cả 1000 lần chạy
print(result["behavioral_results"]) # DataFrame: chỉ các bộ behavioral (NSE ≥ 0.5)
print(f"Behavioral: {result['behavioral_ratio']:.1%}")
```

#### GLUE + 95PPU

```python
# Tính dải bất định 95PPU
unc = calib.glue.uncertainty_band(
    behavioral_df = result["behavioral_results"],
    observed      = obs,
    metric        = "nse",
)
print(f"p-factor: {unc['p_factor']:.3f}")   # ≥ 0.70 → tốt
print(f"r-factor: {unc['r_factor']:.3f}")   # ≤ 1.50 → tốt
unc["uncertainty_band"].plot()               # DataFrame: lower, upper, obs
```

### DDS — Dynamically Dimensioned Search

DDS tự điều chỉnh tỷ lệ perturbation theo tiến độ: `P = 1 - ln(i)/ln(N)`. Hiệu quả với ngân sách ≤ 500 lần chạy.

```python
result = calib.dds.run(
    param_ranges = param_ranges,
    observed     = obs,
    n_iterations = 300,
    r            = 0.2,
    seed         = 42,
    metric       = "nse",
    outputs      = {"FLOW_OUTcms": [1]},
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
    observed        = obs,
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
    param_ranges   = param_ranges,
    observed       = obs,
    n_particles    = 20,
    max_iterations = 50,
    w_max          = 0.9,
    w_min          = 0.4,
    c1             = 2.0,
    c2             = 2.0,
    seed           = 42,
    tol            = 1e-6,
    patience       = 10,
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
    param_ranges = param_ranges,
    observed     = obs,
    method       = "differential_evolution",  # hoặc "minimize" (L-BFGS-B), "Nelder-Mead", "Powell", ...
    metric       = "nse",
    max_iter     = 100,
    on_failure   = "raise",                  # hoặc "penalize": lần chạy lỗi nhận giá trị tệ nhất
)
print(result["best_parameters"])
print(f"Best NSE: {result['best_objective_value']:.4f}")
```

Các thuật toán tuần tự (`calib.optimize`, `calib.dds.run`) mặc định dừng ở lần chạy SWAT lỗi đầu tiên (`on_failure="raise"`). Các thuật toán theo quần thể (GLUE, DE, PSO) cho lần chạy lỗi điểm NaN, luôn xếp cuối; nếu mọi lần chạy trong một lô đều lỗi thì báo `RuntimeError`. Một `method` cục bộ (mọi giá trị khác DE) xuất phát từ giữa khoảng tham số và không thoát được vùng mà mọi lần chạy đều lỗi: hãy dùng DE khi một phần không gian tham số làm SWAT lỗi.

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
    observed        = obs,
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

## Hiệu chỉnh đa trạm

Truyền `observed` dạng dict với khóa `(variable, reach)` để hiệu chỉnh đồng thời nhiều trạm và/hoặc nhiều biến:

```python
observed = {
    ("FLOW_OUTcms", 1):  obs_flow_r1,
    ("FLOW_OUTcms", 5):  obs_flow_r5,
    ("SED_OUTtons", 5):  obs_sed_r5,
}
weights = {
    ("FLOW_OUTcms", 1):  0.4,
    ("FLOW_OUTcms", 5):  0.4,
    ("SED_OUTtons", 5):  0.2,
}

res = project.calibration(
    param_ranges,
    observed     = observed,
    calib_period = ("2005-01-01", "2010-12-31"),
    valid_period = ("2011-01-01", "2015-12-31"),
    metric       = "nse",
    weights      = weights,
    # outputs có thể thêm các trạm không có thực đo để vẫn lưu chuỗi:
    outputs      = {"FLOW_OUTcms": [1, 5, 12], "SED_OUTtons": [5]},
)
```

Quy tắc tính điểm:
- `observed` dạng `pd.Series` đơn nghĩa là một trạm duy nhất và đòi hỏi `outputs` có đúng một `(variable, reach)` (mặc định `{"FLOW_OUTcms": [1]}`).
- Nếu bỏ qua `outputs` khi `observed` là dict, `outputs` được suy ra từ các khóa của `observed`. Các trạm thêm trong `outputs` không có thực đo vẫn được lưu chuỗi vào thư mục phiên chạy nhưng không tính chỉ số.
- `weights` mặc định chia đều cho mọi trạm có thực đo. Trọng số truyền vào phải dương, thuộc các trạm đã biết, và được chuẩn hóa để tổng bằng 1 (trạm không được gán trọng số có trọng số 0 và không tham gia vào `score`).
- Chỉ số từng trạm được tính trên `calib_period` (và `valid_period` nếu có) bằng `evaluate()`. `score` là trung bình có trọng số của chỉ số mục tiêu (`metric`) trên `calib_period` tại các trạm có `weight > 0`, dùng **`|pbias|`** khi `metric="pbias"` (trong khi file chỉ số từng trạm vẫn giữ `pbias` có dấu).
- Chiều tối ưu của bảng đăng ký được giữ nguyên (`score` cùng chiều với `metric`). Chỉ cần một trạm có trọng số bị NaN thì `score` là NaN (lần chạy lỗi xếp cuối). Gộp `rmse` hoặc `mae` qua nhiều biến khác đơn vị mà không truyền `weights` sẽ phát cảnh báo.
- Trước khi chạy SWAT bất kỳ lần nào, mọi trạm thực đo phải giao với `calib_period` và có phương sai khác 0 (báo `ValueError` ngay).

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

## Đánh giá theo giai đoạn

Kiểm định thực chất là đánh giá chuỗi mô phỏng trên một giai đoạn được chọn. `project.evaluate(...)` là hàm **thuần** (không chạy SWAT, không đụng tham số hay file):

```python
ev = project.evaluate(
    sim,                                           # pd.Series hoặc {(variable, reach): pd.Series}
    observed,                                      # cùng dạng với sim
    periods = {
        "calib": ("2005-01-01", "2010-12-31"),
        "valid": ("2011-01-01", "2015-12-31"),
    },
    metrics = ("nse", "kge", "pbias", "r2"),
    step    = None,                                # None hoặc "M"
    agg     = None,                                # {variable: "mean" | "sum"} khi step="M"
)
print(ev.table)          # MultiIndex (variable, reach, period); cột = metrics + n
ev.to_csv("D:/SWAT/evaluation.csv")
```

- `project.evaluate` tự điền bước in (`FileCIO.get_iprint()`) và mốc hết warm-up (`Timestamp(IYR + NYSKIP, 1, 1)`). Giai đoạn bắt đầu trước mốc warm-up hoặc nằm ngoài phạm vi mô phỏng sẽ báo `ValueError`.
- `step="M"` gộp **chuỗi mô phỏng** về ngày đầu tháng (`"MS"`) theo `agg` (mặc định `"mean"`, hoặc `"sum"` cho các biến bắt đầu bằng `SED_` hoặc kết thúc bằng `tons` hay `kg`); số liệu thực đo không bao giờ bị resample.
- Hàm thuần `evaluate(sim, observed, periods=None, *, metrics=..., freq=None, step=None, agg=None, warmup_end=None)` cũng có sẵn trong `spyswat.swat_calib.analysis.evaluate`.

Để ghi tham số đã hiệu chỉnh vào `TxtInOut` một cách tường minh (vd cho một lần chạy SWAT thủ công):

```python
project.apply(res)          # lệnh facade duy nhất ghi tham số vào TxtInOut
project.run()
```

> **Đã đánh dấu lỗi thời (`ValidationRunner`):** `ValidationRunner` và `PeriodConfig` vẫn dùng được kèm `DeprecationWarning` tới **0.4.0**; hãy dùng `project.calibration(..., calib_period=..., valid_period=...)` và `project.evaluate(...)`.

### Bước thời gian của số liệu thực đo

Số liệu thực đo phải có cùng bước thời gian với bước in kết quả của mô hình (`IPRINT` trong `file.cio`, hoặc `"MS"` khi `step="M"`): thực đo ngày cho kết quả ngày, thực đo tháng cho kết quả tháng. SpySWAT không tự gộp thực đo; nếu lệch thì báo `ValueError` trước khi chạy. Thực đo tháng phải đặt ngày **mùng 1**:

```python
obs_monthly = obs_daily.resample("MS").mean()                 # lưu lượng: trung bình tháng
# hoặc, nếu đã là số liệu tháng nhưng đặt ở cuối tháng:
obs.index = obs.index.to_period("M").to_timestamp()

from spyswat.swat_calib.calibration.calib_manager import check_observation_step
check_observation_step(obs.index, project.FileCIO.get_iprint())   # báo lỗi nếu lệch
```

---

## Thư mục phiên chạy & Nhật ký lần chạy

`project.calibration(...)` lưu mọi lần chạy vào một thư mục phiên riêng dưới `results_dir` (mặc định `<working_dir>/calibration_results/<YYYYMMDD_HHMMSS>_<algorithm>_<metric>`):

```
<results_dir>/<session>/
├── session.json                 chữ ký phiên (algorithm, metric(s), seed, param_ranges, periods, step, observed_hash, ...)
├── runs.csv                     mỗi lần chạy một dòng: run_id, time, status, error, is_initial, <params...>, score
├── best.csv                     bộ tham số tốt nhất (parameter, value)
├── sensitivity.csv              độ nhạy hồi quy OLS (khi được tính)
└── reach_<id>/
    ├── <variable>.csv           date, run_<n>, ... (tách file tại 16 000 cột → <variable>_part2.csv)
    └── <variable>_metrics.csv   run_id, <metric>_calib, <metric>_valid, ...
```

Mở lại bất kỳ phiên chạy đã lưu nào bằng `CalibrationResult.load(session_dir)` (metadata đọc ngay; chuỗi mô phỏng và chỉ số từng trạm được đọc chậm qua `res.series(variable, reach)` và `res.site_metrics(variable, reach)`).

Các hàm cấp thấp (`CalibrationManager.run_iteration`, `run_batch`, `record_run`) vẫn ghi nối vào cặp file phẳng `<session>_metrics.csv` và `<session>_outputs.csv` qua `RunLog` khi không truyền `SessionStore`:

```python
manager = calib.manager
manager.log_outputs = "observed"          # "all" (mặc định) | "observed" (ngày có thực đo) | "none"
manager.results_dir = "D:/SWAT/results"   # None để tắt nhật ký
print(manager.session_files)              # {'metrics': Path, 'outputs': Path}

# thuật toán tự viết, tự chạy SWAT:
manager.record_run({"CN2.mgt": 75.0}, {"nse": 0.71}, sim=sim_series)
```

Nhật ký không bao giờ làm dừng quá trình hiệu chỉnh: nếu file bị khóa (ví dụ đang mở trong Excel), các dòng được giữ trong bộ nhớ, cảnh báo một lần, và ghi ở lần flush tiếp theo hoặc khi gọi `manager.flush_log()`.

---

## Chạy theo kịch bản

Chạy nhiều **kịch bản** (bản đồ sử dụng đất, dữ liệu khí hậu, giai đoạn mô phỏng) với nhiều **bộ tham số** song song, xuất chuỗi kết quả và chỉ số.

```python
from spyswat.swat_calib.scenarios import Scenario, ParamSet, ScenarioBatch

if __name__ == "__main__":
    scenarios = [
        Scenario("LUC2000", txinout_dir="D:/SWAT/LUC2000/TxtInOut"),   # TxtInOut đầy đủ
        Scenario("LUC2020", txinout_dir="D:/SWAT/LUC2020/TxtInOut"),
        Scenario("GCM_ssp245", weather_dir="D:/GCM/ssp245",            # chép đè lên TxtInOut gốc
                 cio={"IYR": 2030, "NBYR": 20, "NYSKIP": 0},
                 evaluate=False),                                     # tương lai: không tính chỉ số
    ]
    param_sets = [
        ParamSet.from_dict("best", {"CN2.mgt": (-0.1, "r"), "ALPHA_BF.gw": 0.5}),
        ParamSet.from_dataframe(table, "par1", param="PARAM", method="method",
                                value="MIN", sub="SUBBASIN"),
    ]

    res = project.scenarios(
        scenarios,
        param_sets,                       # cũng nhận res.top(10), res.select(...), hoặc CalibrationResult
        outputs     = {"FLOW_OUTcms": [51, 55], "SED_OUTtons": [51]},
        observed    = {("FLOW_OUTcms", 51): obs},
        results_dir = "D:/SWAT/results",
        metrics     = ("nse", "kge", "pbias"),
        # pairs=[("LUC2000", "best")],   # mặc định: mọi kịch bản × mọi bộ tham số
        resume      = True,              # bỏ qua việc đã 'ok' trong summary.csv
    )
    print(res.summary)      # job_id, scenario, param_set, status, error, duration_s, ...
    print(res.metrics)      # job_id, scenario, param_set, variable, reach, metric, value
    res.to_csv("FLOW_OUTcms", "D:/SWAT/results/flow_all.csv")
```

| Tùy chọn | Ý nghĩa |
|----------|---------|
| `Scenario(txinout_dir=...)` | Một thư mục TxtInOut riêng, đầy đủ |
| `Scenario(weather_dir=...)` | Các file được chép đè theo tên lên TxtInOut gốc (phải đúng định dạng SWAT sẵn) |
| `Scenario(cio={...})` | Ghi đè `file.cio`: `NBYR`, `IYR`, `IDAF`, `IDAL`, `IPRINT`, `NYSKIP` |
| `Scenario(evaluate=False)` | Kịch bản tương lai / GCM: vẫn ghi chuỗi, không tính chỉ số, không kiểm bước thời gian |
| `resume=True` | Bỏ qua việc đã xong; báo lỗi nếu outputs, metrics, thực đo, định nghĩa kịch bản hoặc file đầu vào TxtInOut của kịch bản đã đổi |

Toàn bộ lô chạy trên một process pool duy nhất với tối đa `n_parallel` thư mục worker (`_scenario_batch/TxInOut1..N`): slot nào xong sẽ nhận ngay việc tiếp theo (ưu tiên việc cùng TxtInOut gốc trước khi chép lại gốc khác). Kết quả được lưu vào `metrics.csv` và `summary.csv` theo tiến độ và khi thoát (kể cả khi nhấn `KeyboardInterrupt`). Một việc lỗi, `weather_dir` không đọc được, thư mục gốc lỗi hoặc worker pool bị gãy chỉ đánh dấu `status="failed"` cho các việc bị ảnh hưởng và `run()` vẫn trả về kết quả, nên `resume=True` có thể chạy lại chúng. Tên chỉ gồm chữ, số, `.`, `_`, `-` và không được chứa `__`. Ví dụ đầy đủ: `docs/sample_run_scenarios.py`.

---

## Phân tích độ nhạy

### Độ nhạy hồi quy từ các lần chạy hiệu chỉnh (0 lần chạy SWAT thêm)

`project.calibration(..., sensitivity=True)` (mặc định) tính hồi quy OLS của `score` theo các tham số chuẩn hóa về `[0, 1]` và lưu vào `res.sensitivity` (`parameter`, `coef`, `t_stat`, `p_value`, `rank` theo `|t|`, kèm `r2`, `n_used`, `n_dropped` trong `.attrs`). Với GLUE dùng tất cả lần chạy; với PSO/DE/DDS chỉ dùng quần thể ngẫu nhiên ban đầu (`is_initial=True`).

Tính lại từ bất kỳ phiên đã lưu nào mà không cần chạy SWAT:

```python
sens_df = project.sensitivity(from_session=res.session_dir)
```

Hoặc gọi trực tiếp `method="regression"`, hay dùng `regression_sensitivity(runs, param_ranges)` trong `spyswat.swat_calib.analysis.regression_sensitivity`.

### Từ kết quả GLUE (Spearman / PRCC)

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
oat_df, indices = project.sensitivity(
    param_ranges,
    observed = obs,
    method   = "oat",
    n_steps  = 10,
    metric   = "nse",
)
print(indices)
# parameter  metric_range  metric_std  range_over_std  sensitivity_index   (xếp giảm dần)
```

`sensitivity_index` = khoảng biến thiên chỉ số của tham số chia cho khoảng lớn nhất trong mọi tham số (tham số ảnh hưởng nhất được 1.0). Lần chạy lỗi bị loại; tham số có ít hơn 2 lần chạy thành công nhận NaN. Khi không truyền `observed`, OAT và Morris khôi phục đầu vào của bạn sau mỗi lần chạy.

### Morris Method (song song)

```python
morris = project.sensitivity(
    param_ranges,
    observed       = obs,
    method         = "morris",
    n_trajectories = 10,
    metric         = "nse",
)
print(morris["morris_indices"])
```

Quỹ đạo nào có lần chạy lỗi sẽ bị loại khỏi chỉ số Morris. `sens = SWATSensitivity(project); sens.sobol_method(...)` (hoặc `project.sensitivity(..., method="sobol")`) báo `RuntimeError` nếu có lần chạy lỗi, vì chỉ số Sobol cần đủ mẫu; lô chạy tốn kém không bị mất: `sens.last_samples` và `sens.last_scores` (NaN = lỗi) vẫn giữ lại. `morris_salib` và `sobol_method` cần `pip install SALib`.

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

### Ghi nghiêm ngặt

File đầu vào được đọc/ghi giữ nguyên từng byte (latin-1, giữ kiểu xuống dòng gốc). Giá trị rộng hơn ô fixed-width, dòng quá ngắn hoặc vị trí cắt nằm ngoài dòng sẽ báo `SWATFileFormatError` và không đụng tới file; mỗi file được thay thế nguyên tử một lần cho mỗi lần gọi `update_params`. Khóa tham số không có trong file tham số báo `ValueError` trước khi sửa bất kỳ file nào.

Thiết lập mô phỏng trong `file.cio`:

```python
project.FileCIO.set(IYR=2000, NBYR=16, NYSKIP=2, IPRINT=0)   # IPRINT: 0 tháng, 1 ngày, 2 năm
project.FileCIO.get_iprint()                                 # 'MS' | 'D' | 'YS'
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

`read_rch` đọc bước in từ `file.cio` và tách file tháng thành các khối tháng (bỏ dòng năm và trung bình năm). Kết quả được cache theo dấu file (thời điểm sửa và kích thước), nên lần chạy SWAT mới luôn được đọc lại; `project.run()` cũng xóa cache. Lỗi phân tích nêu rõ file, dòng và cột.

```python
project.Output.check_complete(".rch")   # báo RuntimeError kèm lý do nếu output.rch không dùng được
project.Output.invalidate()             # xóa cache thủ công
```

---

## Thống kê hiệu suất

```python
stats  = project.Statistic.calculate_statistics(obs, sim,
    metrics=["nse", "kge", "r2", "rmse", "pbias", "rsr"])
rating = project.Statistic.evaluate_performance(obs, sim)
```

Một bảng đăng ký duy nhất (`spyswat.swat_calib.analysis.statistics.METRIC_DIRECTIONS`) cho mọi thuật toán biết chiều tốt của từng chỉ số:

| Chiều | Chỉ số |
|-------|--------|
| càng lớn càng tốt | `nse`, `kge`, `r2`, `correlation` |
| càng nhỏ càng tốt | `rmse`, `mae`, `rsr` |
| càng gần 0 càng tốt | `pbias` (tối ưu theo `abs(pbias)`) |

Hàm hỗ trợ: `known_metrics()`, `is_maximize(m)`, `to_objective(m, score)` (luôn càng nhỏ càng tốt), `best_index(scores, m)` (an toàn với NaN). Tên chỉ số không có trong bảng báo `ValueError`.

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


scores = manager.run_batch(
    param_sets = [
        {"CN2.mgt": [(70.0, "v")]},
        {"CN2.mgt": [(75.0, "v")]},
        {"CN2.mgt": [(80.0, "v")]},
    ],
    observed = obs,
    metrics  = ("nse",),
    outputs  = {"FLOW_OUTcms": [1]},
)
print(scores)   # danh sách float (NaN cho lần chạy lỗi)
```

Mọi lần chạy song song đều bảo đảm:

- **Khôi phục gốc trước:** mỗi worker chép lại file đầu vào từ TxtInOut của bạn trước khi áp tham số, nên thay đổi tương đối (`r`) và cộng (`a`) không bị cộng dồn qua các lô. TxtInOut của bạn không bao giờ bị sửa.
- **Cô lập lỗi:** lần chạy bị lỗi, quá thời gian hoặc không sinh output mới được báo là lỗi (`WorkerResult(ok=False, error=...)`) và nhận điểm NaN; không bao giờ đọc output cũ như output mới.
- **Dừng sạch:** Ctrl+C kết thúc các tiến trình SWAT con (`taskkill /T` trên Windows).

Hook cấp thấp cho quy trình tự viết: `project.WorkingFolder.run_parallel(swat_exe, param_sets, prepare=..., extract=..., overlays=..., timeout_s=...)`. `prepare`/`extract` nhận một hàm hoặc danh sách một hàm cho mỗi việc; phải là hàm cấp module (picklable).

---

## API Reference

### SWATProject

```
# Facade 0.3.0
project.calibration(param_ranges, observed, calib_period, valid_period=None, *,
                    algorithm="glue", metric="nse", metrics=("nse", "kge", "pbias", "r2"),
                    weights=None, outputs=None, step=None, agg=None, n_parallel=None,
                    seed=None, results_dir=None, session=None, resume=True,
                    sensitivity=True, param_methods=None, param_subbasins=None,
                    **algorithm_options) → CalibrationResult
project.evaluate(sim, observed, periods=None, *, metrics=..., step=None, agg=None) → EvaluationResult
project.sensitivity(param_ranges=None, observed=None, method="morris", *,
                    from_session=None, **options)
project.scenarios(scenarios, param_sets, outputs, observed=None, results_dir=None,
                  **options) → BatchResult
project.apply(x, methods=None, subbasins=None)   # ghi tham số vào TxtInOut

# Các manager & tiện ích cấp thấp
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
project.HRU.validate_inputs(params=None) → DataFrame các lỗi (rỗng = OK)
project.FileCIO.get_date_range_sim(freq)
project.FileCIO.get_iprint() → 'MS' | 'D' | 'YS'
project.FileCIO.set(NBYR=, IYR=, IDAF=, IDAL=, IPRINT=, NYSKIP=)
project.Output.check_complete(file_type=".rch") / invalidate()
project.WorkingFolder.setup(overwrite)
project.WorkingFolder.run_parallel(swat_exe, param_sets, prepare=, extract=,
                                   overlays=, timeout_s=) → [WorkerResult]
project.info()
```

### Đánh giá thuần & Độ nhạy hồi quy

```python
from spyswat.swat_calib.analysis.evaluate import evaluate, EvaluationResult
from spyswat.swat_calib.analysis.regression_sensitivity import regression_sensitivity

evaluate(sim, observed, periods=None, *, metrics=("nse", "kge", "pbias", "r2"),
         freq=None, step=None, agg=None, warmup_end=None) → EvaluationResult
regression_sensitivity(runs, param_ranges, score_col="score") → pd.DataFrame
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
               param_methods, param_subbasins, on_failure="raise") → dict

# Hạ tầng
calib.manager                          # CalibrationManager
calib.manager.run_once(params, *, outputs=None, methods=None, subbasins=None) → {(variable, reach): Series}
calib.manager.run_iteration(param_dict, observed, metric=None, methods=None, subbasins=None, *,
                            outputs=None, weights=None, metrics=None, calib_period=None,
                            valid_period=None, step=None, agg=None, store=None,
                            run_id=None, is_initial=False) → float
calib.manager.run_batch(param_sets, observed, metrics=None, methods=None, subbasins=None, *,
                        metric=None, outputs=None, weights=None, calib_period=None,
                        valid_period=None, step=None, agg=None, store=None,
                        run_ids=None, is_initial=False) → DataFrame
calib.manager.record_run(params, scores, *, status="ok", error=None, sim=None, ...)
calib.manager.flush_log() → bool
calib.manager.results_dir / log_outputs / session_files
```

### ValidationRunner (lỗi thời — bỏ ở 0.4.0)

Dùng `project.calibration(..., calib_period=..., valid_period=...)` và `project.evaluate(...)`.

### Scenarios

```
from spyswat.swat_calib.scenarios import Scenario, ParamSet, ScenarioBatch

Scenario(name, txinout_dir=None, weather_dir=None, cio=None, evaluate=True)
ParamSet(name, updates={"CN2.mgt": [(value, method[, subbasins]), ...]})
ParamSet.from_dict(name, {"CN2.mgt": 75.0, "ESCO.hru": (0.1, "r")})
ParamSet.from_dataframe(df, name, param="param", method="method", value="value", sub="subbasin")

ScenarioBatch(project, results_dir)
  .run(scenarios, param_sets, *, outputs, pairs=None, observed=None,
       metrics=("nse", "kge", "pbias"), resume=True, timeout_s=None) → BatchResult
BatchResult: .summary, .metrics, .results, .failed, .warnings,
             .series(variable) → DataFrame, .to_csv(variable, path) → Path
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
│       ├── calibration/ CalibrationManager, scoring, session_store, result, run_log,
│       │               ValidationRunner (lỗi thời)
│       ├── scenarios/  Scenario, ParamSet, ScenarioBatch
│       ├── analysis/   SWATAnalysis + bảng chỉ số, evaluate, regression_sensitivity,
│       │               SWATCalibration (facade), SWATSensitivity
│       │               └── algorithms/  dds.py, glue.py, parallel_de.py, pso.py
│       ├── run/        SWATRun (tiến trình con, timeout)
│       └── visualization/ FigViewer
├── docs/               sample_run_single.py, sample_run_parallel.py, sample_run_scenarios.py
├── tests/              475 tests (464 passed, 11 skipped trên Windows; không cần SWAT.exe)
├── .agents/            sổ ghi chép theo đầu việc, commit cùng code (xem AGENTS.md)
├── AGENTS.md           hướng dẫn cho AI agent và người đóng góp (CLAUDE.md nạp tệp này)
├── ARCHITECTURE.md     Kiến trúc chi tiết + sơ đồ kết nối
└── pyproject.toml
```

---

## Tests

```bash
pytest tests/ -q
# 464 passed, 11 skipped (~4 phút trên Windows)
```

Test bị bỏ qua trên Windows: test dùng script POSIX làm exe giả (`tests/test_run.py`) và test SALib khi chưa cài SALib.

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
