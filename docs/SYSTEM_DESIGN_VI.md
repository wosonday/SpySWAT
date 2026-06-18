# Thiết kế hệ thống SpySWAT — Mở rộng Hiệu chỉnh, Kiểm định và Phân tích Độ nhạy

**Phiên bản:** 1.0 (tài liệu thiết kế lịch sử — phản ánh ý định thiết kế ban đầu)  
**Ngày:** 2026-06-10  
**Phiên bản triển khai hiện tại:** v0.2.6 — xem [ARCHITECTURE.md](../ARCHITECTURE.md) để biết trạng thái hiện tại  
**Phạm vi:** Thiết kế kiến trúc mở rộng cho module calibration, validation và sensitivity analysis  

> **Lưu ý:** Đây là tài liệu thiết kế lịch sử được viết trước khi triển khai. Tất cả các khoảng cách (gaps) ở §2–§3 đã được giải quyết. Tập thuật toán hiện tại: GLUE, Parallel DE, DDS, PSO (v0.2.6). Xem [ARCHITECTURE.md](../ARCHITECTURE.md) và [README_VI.md](../README_VI.md) để biết API cập nhật.

---

## Mục lục

1. [Bối cảnh và mục tiêu](#1-bối-cảnh-và-mục-tiêu)
2. [Kiểm tra hiện trạng hệ thống](#2-kiểm-tra-hiện-trạng-hệ-thống)
3. [Phân tích khoảng cách (Gap Analysis)](#3-phân-tích-khoảng-cách-gap-analysis)
4. [Điểm cốt lõi trong thiết kế](#4-điểm-cốt-lõi-trong-thiết-kế)
5. [Kiến trúc mục tiêu](#5-kiến-trúc-mục-tiêu)
6. [Thiết kế chi tiết từng module](#6-thiết-kế-chi-tiết-từng-module)
   - [6.1 CalibrationManager — Lớp giao dịch cốt lõi](#61-calibrationmanager--lớp-giao-dịch-cốt-lõi)
   - [6.2 ValidationRunner — Hiệu chỉnh + Kiểm định 2 giai đoạn](#62-validationrunner--hiệu-chỉnh--kiểm-định-2-giai-đoạn)
   - [6.3 SWATCalibration — Tối ưu hóa tham số](#63-swatcalibration--tối-ưu-hóa-tham-số)
   - [6.4 SWATSensitivity — Phân tích độ nhạy song song](#64-swatsensitivity--phân-tích-độ-nhạy-song-song)
7. [Luồng dữ liệu tổng thể](#7-luồng-dữ-liệu-tổng-thể)
8. [Thứ tự triển khai và tiêu chí xác minh](#8-thứ-tự-triển-khai-và-tiêu-chí-xác-minh)
9. [Các quyết định thiết kế và đánh đổi](#9-các-quyết-định-thiết-kế-và-đánh-đổi)
10. [Tài liệu tham khảo khoa học](#10-tài-liệu-tham-khảo-khoa-học)

---

## 1. Bối cảnh và mục tiêu

SpySWAT hiện cung cấp khả năng đọc/ghi file SWAT và chạy mô hình đơn lẻ. Mục tiêu mở rộng là tích hợp toàn bộ quy trình khoa học thủy văn tiêu chuẩn:

```
Phân tích độ nhạy → Hiệu chỉnh → Kiểm định → Đánh giá bất định
```

Đây là quy trình được quy định bởi **Moriasi et al. (2007)** và là điều kiện tiên quyết để công bố kết quả mô hình SWAT trong nghiên cứu khoa học.

**Mục tiêu cụ thể:**
- Xác định tham số có ảnh hưởng lớn nhất đến output (sensitivity)
- Tìm bộ tham số tối ưu để output khớp với quan trắc (calibration)
- Kiểm tra tính tổng quát của mô hình trên dữ liệu độc lập (validation)
- Ước lượng bất định của dự báo (uncertainty — GLUE)

---

## 2. Kiểm tra hiện trạng hệ thống

### Những gì đang hoạt động thực sự

| Module | Trạng thái | Ghi chú |
|--------|-----------|---------|
| `TxInOut` | ✅ Hoạt động | Filesystem abstraction tốt |
| `HRUManager.update_params()` | ✅ Hoạt động | Ghi file fixed-width đúng |
| `OutputFileManager` | ✅ Hoạt động | Cache DataFrame theo filepath |
| `FileCIO` | ✅ Hoạt động | Đọc/cập nhật file.cio |
| `SWATAnalysis` | ✅ Hoạt động | NSE, KGE, PBIAS, R², RMSE |
| `WorkingFolderManager` | ✅ Hoạt động | Copy + chạy song song subprocess |

### Những gì có skeleton nhưng không dùng được

| Module | Vấn đề thực tế |
|--------|---------------|
| `CalibrationManager` | `_backup_state`, `_restore_state`, `_align_series` là `...` (stub rỗng hoàn toàn) |
| `SWATCalibration` | `self._manager = None` → `optimize()` crash khi gọi `_manager.run_iteration()` |
| `SWATSensitivity` | Gọi `project.update_parameters()` và `project.output.read_reach()` — **hai method này không tồn tại** trên `SWATProject` |
| `SWATRun.run()` | Nhận `txinout_path: str` nhưng dùng operator `/` (Path) → `TypeError` ngay lập tức |

### Lỗi logic đã phát hiện

- `OutputFileManager.read_sed()` dùng nhầm constant `_SUB_DEFAULT_COLS` thay vì `_SED_DEFAULT_COLS`
- `mapping_output.py` line 112: `raise logger.exception(...)` → `raise None` (logger.exception trả về None)
- `statistics.py` có 3 lệnh `print()` debug trong `_nse()` chưa được xóa

---

## 3. Phân tích khoảng cách (Gap Analysis)

### Khoảng cách chức năng

```
CẦN CÓ                          HIỆN TẠI
─────────────────────────────    ────────────────────────────
Backup TxtInOut trước ghi     ←  Ghi đè trực tiếp, không backup
Transaction rollback           ←  Không có
Time-series alignment          ←  Stub rỗng
Calibration loop hoàn chỉnh   ←  _manager = None
Validation 2 giai đoạn        ←  Không tồn tại
Sensitivity parallel           ←  Chạy tuần tự, gọi API sai
```

### Khoảng cách giao diện (Interface mismatch)

`SWATCalibration` và `SWATSensitivity` được viết để gọi:
```python
self.project.update_parameters(params)     # KHÔNG TỒN TẠI
self.project.output.read_reach(reach_id)   # KHÔNG TỒN TẠI
self.project.run(clear_output_cache=True)  # SAI SIGNATURE
```

API thực tế trên `SWATProject` là:
```python
self.project.HRU.update_params(params)                            # đúng
self.project.Output.read_rch(columns=[...], reach_id=reach_id)   # đúng
self.project.run()                                                 # đúng
```

---

## 4. Điểm cốt lõi trong thiết kế

> **Mỗi lần ghi tham số vào TxtInOut là một thao tác không thể hoàn tác (destructive write). Nếu vòng lặp hiệu chỉnh thất bại giữa chừng, một số file đã bị ghi đè trong khi số còn lại chưa → trạng thái TxtInOut không nhất quán → mô hình cho kết quả sai hoặc crash mà không có cảnh báo.**

Đây là lý do `CalibrationManager` là **ranh giới giao dịch (transaction boundary)** duy nhất và quan trọng nhất trong hệ thống. Toàn bộ kiến trúc mở rộng xoay quanh việc implement đúng component này.

**Nguyên tắc thiết kế:**

1. **Atomic write** — Mọi cập nhật tham số phải có backup trước, restore khi thất bại
2. **Fail loudly** — Lỗi trong vòng lặp phải được raise rõ ràng, không nuốt exception
3. **Parallel by default** — Sensitivity analysis là embarrassingly parallel; `WorkingFolderManager` đã có sẵn, không cần thiết kế thêm
4. **Không thêm abstraction mới** — Kiến trúc hiện tại đủ tốt; vấn đề là kết nối bị đứt, không phải thiếu tầng

---

## 5. Kiến trúc mục tiêu

```
SWATProject  (giữ nguyên — không thay đổi interface)
│
├── [SỬA] SWATRun.run()               → Fix type: str → Path
│
└── CalibrationManager                 [IMPLEMENT — cốt lõi]
    │  backup_state / restore_state / align_series
    │
    ├── CalibRunner                    [wrapper đơn giản]
    │     run_iteration()
    │     → backup → update_params → run → evaluate → (restore nếu lỗi)
    │
    ├── ValidationRunner               [MỚI]
    │     calibrate(period_calib)
    │     validate(period_valid)
    │     → trả về: calib_stats + valid_stats + best_params
    │
    ├── [SỬA] SWATCalibration          → nối _manager thật
    │     optimize()                   → differential_evolution, nelder-mead
    │     glue_analysis()              → Monte Carlo + uncertainty bounds
    │
    └── [SỬA] SWATSensitivity          → nối đúng API + parallel
          one_at_a_time()              → dùng WorkingFolderManager
          morris_method()              → dùng WorkingFolderManager
```

**Cấu trúc thư mục sau khi mở rộng:**

```
spyswat/
├── swat_project.py                    (không đổi)
├── swat_calib/
│   ├── calibration/
│   │   ├── calib_manager.py           ← IMPLEMENT
│   │   ├── validation_runner.py       ← MỚI
│   │   └── __init__.py
│   ├── analysis/
│   │   ├── calibration.py             ← SỬA (_manager)
│   │   ├── sensitivity.py             ← SỬA (API + parallel)
│   │   └── statistics.py              ← xóa print() debug
│   └── run/
│       └── run.py                     ← SỬA (str → Path)
```

---

## 6. Thiết kế chi tiết từng module

### 6.1 CalibrationManager — Lớp giao dịch cốt lõi

**Trách nhiệm:** Đảm bảo mọi iteration đều atomic — thành công hoàn toàn hoặc không thay đổi gì.

```python
# spyswat/swat_calib/calibration/calib_manager.py

import shutil, tempfile
from pathlib import Path
import pandas as pd
from spyswat.logger import Logger

logger = Logger.get_logger(__name__)


class CalibrationManager:
    """
    Transaction boundary cho mọi thao tác ghi tham số + chạy SWAT.

    Đảm bảo: nếu run_iteration() thất bại tại bất kỳ bước nào,
    TxtInOut được khôi phục về trạng thái trước đó.
    """

    def __init__(self, project):
        self.project = project
        self._backup_dir: Path | None = None

    # ─── Public API ───────────────────────────────────────────

    def run_iteration(
        self,
        param_dict: dict,
        observed: pd.Series,
        metric: str = 'nse',
        reach_id: int = 1,
        output_variable: str = 'FLOW_OUTcms'
    ) -> float:
        """
        Chạy một vòng lặp hiệu chỉnh:
          1. Backup TxtInOut
          2. Ghi tham số mới
          3. Chạy SWAT
          4. Đọc output, tính metric
          5. Nếu lỗi: khôi phục backup, raise

        Returns:
            Giá trị metric (float) — cao hơn = tốt hơn với NSE, KGE, R²
        Raises:
            RuntimeError: nếu SWAT crash hoặc đọc output thất bại
        """
        self._backup_state()
        try:
            self.project.HRU.update_params(param_dict)
            self.project.run()

            # Invalidate cache để đọc output mới
            self.project.Output.cache.clear()

            sim = self.project.Output.read_rch(
                columns  = ['RCH', 'MON', output_variable],
                reach_id = reach_id
            )[output_variable]

            obs_aligned, sim_aligned = self._align_series(observed, sim)
            score = self.project.Statistic.calculate_statistics(
                obs_aligned, sim_aligned, metrics=[metric]
            )[metric]

            logger.info(f"Iteration {metric}={score:.4f} | params={param_dict}")
            return float(score)

        except Exception as e:
            logger.warning(f"Iteration failed, restoring TxtInOut: {e}")
            self._restore_state()
            raise RuntimeError(f"Iteration failed: {e}") from e

    # ─── Transaction helpers ──────────────────────────────────

    def _backup_state(self) -> None:
        """Copy toàn bộ TxtInOut vào thư mục tạm."""
        if self._backup_dir and self._backup_dir.exists():
            shutil.rmtree(self._backup_dir)

        tmp = Path(tempfile.mkdtemp(prefix="spyswat_backup_"))
        shutil.copytree(self.project.txinout.directory, tmp / "TxtInOut")
        self._backup_dir = tmp
        logger.debug(f"Backup created at: {self._backup_dir}")

    def _restore_state(self) -> None:
        """Khôi phục TxtInOut từ backup."""
        if self._backup_dir is None:
            logger.warning("No backup available to restore.")
            return

        src = self._backup_dir / "TxtInOut"
        dst = self.project.txinout.directory

        shutil.rmtree(dst)
        shutil.copytree(src, dst)
        logger.info(f"TxtInOut restored from: {src}")

    def _align_series(
        self, obs: pd.Series, sim: pd.Series
    ) -> tuple[pd.Series, pd.Series]:
        """
        Căn chỉnh chuỗi thời gian quan trắc và mô phỏng theo index ngày.

        sim được gắn DatetimeIndex từ FileCIO, sau đó lấy giao với obs.
        """
        date_range = self.project.get_date_range(freq='D')
        sim = sim.reset_index(drop=True)

        if len(sim) != len(date_range):
            raise ValueError(
                f"Simulated length ({len(sim)}) ≠ date_range ({len(date_range)}). "
                "Kiểm tra lại file.cio và output.rch."
            )

        sim.index = date_range
        common_idx = obs.index.intersection(sim.index)

        if len(common_idx) == 0:
            raise ValueError(
                "Không có ngày chung giữa quan trắc và mô phỏng. "
                "Kiểm tra lại khoảng thời gian trong file.cio."
            )

        return obs.loc[common_idx], sim.loc[common_idx]

    def cleanup(self) -> None:
        """Xóa thư mục backup tạm."""
        if self._backup_dir and self._backup_dir.exists():
            shutil.rmtree(self._backup_dir)
            self._backup_dir = None
```

**Quyết định thiết kế:** Backup toàn bộ thư mục thay vì chỉ backup file được sửa.

- **Lý do:** Đơn giản hơn, đảm bảo tính nhất quán tuyệt đối. Một lần chạy SWAT thường mất vài giây đến vài phút — overhead của `shutil.copytree` (< 1 giây cho TxtInOut điển hình ~50MB) không đáng kể.
- **Đánh đổi:** Dùng nhiều disk hơn. Có thể tối ưu sau nếu TxtInOut lớn.

---

### 6.2 ValidationRunner — Hiệu chỉnh + Kiểm định 2 giai đoạn

**Trách nhiệm:** Tách dữ liệu quan trắc thành 2 giai đoạn, hiệu chỉnh trên giai đoạn 1, kiểm định trên giai đoạn 2.

```python
# spyswat/swat_calib/calibration/validation_runner.py

from dataclasses import dataclass
from typing import Dict, Tuple
import pandas as pd
from spyswat.logger import Logger

logger = Logger.get_logger(__name__)


@dataclass
class PeriodConfig:
    """
    Cấu hình giai đoạn hiệu chỉnh và kiểm định.

    Attributes:
        calib_start: Ngày bắt đầu hiệu chỉnh (YYYY-MM-DD)
        calib_end:   Ngày kết thúc hiệu chỉnh
        valid_start: Ngày bắt đầu kiểm định
        valid_end:   Ngày kết thúc kiểm định
    """
    calib_start: str
    calib_end:   str
    valid_start: str
    valid_end:   str


class ValidationRunner:
    """
    Chạy quy trình hiệu chỉnh → kiểm định tiêu chuẩn (Moriasi et al., 2007).

    Example:
        >>> period = PeriodConfig('1990-01-01', '2000-12-31',
        ...                       '2001-01-01', '2010-12-31')
        >>> runner = ValidationRunner(project, param_ranges, observed, period)
        >>> result = runner.run(metric='nse', max_iter=100, reach_id=8)
        >>> print(result['calibration'])  # {'nse': 0.74}
        >>> print(result['validation'])   # {'nse': 0.68, 'kge': 0.71, ...}
    """

    def __init__(
        self,
        project,
        param_ranges: Dict[str, Tuple[float, float]],
        observed:     pd.Series,
        period:       PeriodConfig
    ):
        self.project      = project
        self.param_ranges = param_ranges
        self.observed     = observed
        self.period       = period

    def run(
        self,
        metric:    str = 'nse',
        method:    str = 'differential_evolution',
        max_iter:  int = 100,
        reach_id:  int = 1,
        output_variable: str = 'FLOW_OUTcms'
    ) -> Dict:
        """
        Luồng thực thi:
          1. Lọc quan trắc theo giai đoạn hiệu chỉnh
          2. Tối ưu hóa tham số (SWATCalibration.optimize)
          3. Áp dụng tham số tốt nhất
          4. Lọc quan trắc theo giai đoạn kiểm định
          5. Đánh giá toàn bộ chỉ số thống kê

        Returns:
            {
                'best_parameters': {...},
                'calibration': {'nse': 0.74, ...},
                'validation':  {'nse': 0.68, 'kge': 0.71, ...},
                'period': PeriodConfig
            }
        """
        # ── Giai đoạn 1: Hiệu chỉnh ──────────────────────────
        logger.info(f"Bắt đầu hiệu chỉnh: {self.period.calib_start} → {self.period.calib_end}")
        obs_calib = self.observed.loc[self.period.calib_start : self.period.calib_end]

        best_params, calib_score = self._calibrate(
            obs_calib, metric, method, max_iter, reach_id, output_variable
        )
        logger.info(f"Hiệu chỉnh hoàn tất. {metric.upper()} = {calib_score:.4f}")
        logger.info(f"Tham số tốt nhất: {best_params}")

        # ── Giai đoạn 2: Kiểm định ───────────────────────────
        logger.info(f"Bắt đầu kiểm định: {self.period.valid_start} → {self.period.valid_end}")
        self.project.HRU.update_params(best_params)
        self.project.run()
        self.project.Output.cache.clear()

        sim = self.project.Output.read_rch(
            columns  = ['RCH', 'MON', output_variable],
            reach_id = reach_id
        )[output_variable]

        date_range = self.project.get_date_range(freq='D')
        sim = sim.reset_index(drop=True)
        sim.index = date_range

        obs_valid = self.observed.loc[self.period.valid_start : self.period.valid_end]
        common    = obs_valid.index.intersection(sim.index)

        valid_stats = self.project.Statistic.calculate_statistics(
            obs_valid.loc[common], sim.loc[common]
        )
        calib_stats = {metric: calib_score}

        logger.info(f"Kiểm định: NSE={valid_stats.get('nse', float('nan')):.4f}, "
                    f"KGE={valid_stats.get('kge', float('nan')):.4f}")

        return {
            'best_parameters': best_params,
            'calibration':     calib_stats,
            'validation':      valid_stats,
            'period':          self.period,
        }

    def _calibrate(self, obs_calib, metric, method, max_iter, reach_id, output_variable):
        from spyswat.swat_calib.analysis.calibration import SWATCalibration
        calib  = SWATCalibration(self.project)
        result = calib.optimize(
            param_ranges    = self.param_ranges,
            observed_series = obs_calib,
            method          = method,
            metric          = metric,
            max_iter        = max_iter,
            reach_id        = reach_id,
            output_variable = output_variable,
        )
        return result['best_parameters'], result['best_objective_value']
```

---

### 6.3 SWATCalibration — Tối ưu hóa tham số

**Sửa đổi cần thiết:** Thay `self._manager = None` bằng instance thực của `CalibrationManager`.

```python
# spyswat/swat_calib/analysis/calibration.py — phần sửa đổi

class SWATCalibration:
    def __init__(self, project, analysis=None):
        self.project  = project
        self.analysis = analysis or SWATAnalysis(project)
        # SỬA: không còn là None
        from spyswat.swat_calib.calibration import CalibrationManager
        self._manager = CalibrationManager(project)
        self.optimization_history = []

    def optimize(self, param_ranges, observed_series, method='differential_evolution',
                 metric='nse', max_iter=100, reach_id=1,
                 output_variable='FLOW_OUTcms') -> dict:

        names  = list(param_ranges.keys())
        bounds = [param_ranges[n] for n in names]

        def objective(x):
            # Chuyển array → dict với format đúng của HRUManager
            param_dict = {name: [(val, 'v')] for name, val in zip(names, x)}
            score = self._manager.run_iteration(
                param_dict, observed_series, metric, reach_id, output_variable
            )
            self.optimization_history.append({'params': dict(zip(names, x)), 'score': score})
            # scipy minimize → trả về âm nếu cần maximize
            return -score if metric in ('nse', 'r2', 'kge') else score

        if method == 'differential_evolution':
            from scipy.optimize import differential_evolution
            result = differential_evolution(objective, bounds, maxiter=max_iter,
                                            seed=42, tol=1e-4)
        else:
            from scipy.optimize import minimize
            x0     = [(b[0] + b[1]) / 2 for b in bounds]
            result = minimize(objective, x0, method=method, bounds=bounds)

        best_params = {name: [(val, 'v')] for name, val in zip(names, result.x)}
        return {
            'best_parameters':      best_params,
            'best_objective_value': -result.fun,
            'history':              self.optimization_history,
        }
```

---

### 6.4 SWATSensitivity — Phân tích độ nhạy song song

**Vấn đề hiện tại:** Chạy tuần tự, gọi API sai. OAT với 5 tham số × 10 steps = 50 lần chạy SWAT.

**Thiết kế mới:** Mỗi điểm tham số là 1 worker độc lập → dùng `WorkingFolderManager`.

```
Thiết kế parallel cho OAT:

param_sets = [  (CN2=60, ESCO=0.5, ...), (CN2=62, ESCO=0.5, ...),
                (CN2=64, ESCO=0.5, ...), ..., 50 bộ tham số  ]
                        ↓
WorkingFolderManager.setup(n_parallel=50)
                        ↓
ProcessPoolExecutor → 50 workers chạy đồng thời
                        ↓
Đọc output từng worker → tổng hợp DataFrame kết quả
```

**Giao diện mới của `one_at_a_time()`:**

```python
def one_at_a_time(
    self,
    param_ranges:    dict,
    n_steps:         int = 10,
    baseline_params: dict | None = None,
    observed_series: pd.Series | None = None,
    output_variable: str = 'FLOW_OUTcms',
    reach_id:        int = 1,
    metric:          str = 'nse',
    n_parallel:      int = 4,    # ← MỚI: số worker song song
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
        (results_df, sensitivity_df)
        results_df:     columns = [parameter, value, metric]
        sensitivity_df: columns = [parameter, metric_range, sensitivity_index]
                        sorted by sensitivity_index descending
    """
    param_sets = self._build_oat_param_sets(param_ranges, n_steps, baseline_params)

    # Tạo n_parallel workers, chia param_sets vào batches
    wf = WorkingFolderManager(
        txinout     = self.project.txinout,
        working_dir = self.project.working_folder / "sensitivity_oat",
        n_parallel  = min(n_parallel, len(param_sets))
    )
    wf.setup(overwrite=True)
    # ... parallel execution + collect results
```

**Chỉ số độ nhạy được tính:**

| Chỉ số | Công thức | Ý nghĩa |
|--------|-----------|---------|
| `metric_range` | max(metric) - min(metric) | Phạm vi ảnh hưởng tuyệt đối |
| `sensitivity_index` | range / std | Ảnh hưởng chuẩn hóa |
| Morris μ* | mean(\|EE\|) | Tầm quan trọng tổng thể |
| Morris σ | std(EE) | Mức độ phi tuyến / tương tác |

---

## 7. Luồng dữ liệu tổng thể

```
┌─────────────────────────────────────────────────────────────────┐
│                     QUY TRÌNH ĐẦY ĐỦ                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. PHÂN TÍCH ĐỘ NHẠY (SWATSensitivity)                        │
│     param_ranges (rộng) → OAT/Morris (parallel)                  │
│     → sensitivity_df: xếp hạng tham số quan trọng               │
│     → Thu hẹp param_ranges cho bước tiếp theo                   │
│                          ↓                                        │
│  2. HIỆU CHỈNH (SWATCalibration via CalibrationManager)         │
│     param_ranges (hẹp) × observed_calib                          │
│     → differential_evolution / GLUE                              │
│     → best_params + optimization_history                         │
│                          ↓                                        │
│  3. KIỂM ĐỊNH (ValidationRunner)                                 │
│     best_params × observed_valid                                  │
│     → calib_stats + valid_stats                                   │
│     → Báo cáo hiệu năng (Moriasi rating)                        │
│                          ↓                                        │
│  4. PHÂN TÍCH BẤT ĐỊNH — tùy chọn (GLUE)                       │
│     behavioral_params (NSE ≥ threshold)                          │
│     → uncertainty_bounds (5th / 95th percentile)                 │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Ví dụ sử dụng toàn bộ quy trình

```python
from spyswat import SWATProject
from spyswat.swat_calib.calibration import ValidationRunner, PeriodConfig
from spyswat.swat_calib.analysis import SWATSensitivity, SWATCalibration
import pandas as pd

# ── Khởi tạo ──────────────────────────────────────────────────
project = SWATProject(
    txinout_dir = r"D:\MyProject\TxtInOut",
    working_dir = r"D:\MyProject\working",
    swat_exe    = r"D:\tools\swat_695.exe",
    param_file  = r"D:\MyProject\swatParam.txt",
    n_parallel  = 8
)

obs = pd.read_csv("Q_observed.csv", index_col='date', parse_dates=['date'])['discharge']

# ── Bước 1: Phân tích độ nhạy ─────────────────────────────────
param_ranges_wide = {
    'CN2':       (55.0, 95.0),
    'ESCO':      (0.0,  1.0),
    'ALPHA_BF':  (0.0,  1.0),
    'GW_DELAY':  (0.0, 500.0),
    'SOL_AWC':   (-0.5, 0.5),   # relative method
    'CH_N2':     (0.01, 0.3),
}

sensitivity = SWATSensitivity(project)
results_df, sensitivity_df = sensitivity.one_at_a_time(
    param_ranges    = param_ranges_wide,
    n_steps         = 10,
    observed_series = obs,
    metric          = 'nse',
    reach_id        = 8,
    n_parallel      = 6
)
print(sensitivity_df.head(4))
# parameter    metric_range    sensitivity_index
# CN2          0.42            3.8
# ALPHA_BF     0.31            2.7
# ESCO         0.18            1.5
# GW_DELAY     0.09            0.8

# ── Bước 2 + 3: Hiệu chỉnh và Kiểm định ─────────────────────
# Chỉ dùng 4 tham số nhạy nhất
param_ranges_narrow = {
    'CN2':      (60.0, 90.0),
    'ALPHA_BF': (0.0,  1.0),
    'ESCO':     (0.5,  1.0),
    'GW_DELAY': (0.0, 200.0),
}

period = PeriodConfig(
    calib_start = '1990-01-01', calib_end = '2004-12-31',
    valid_start = '2005-01-01', valid_end = '2019-12-31'
)

runner = ValidationRunner(project, param_ranges_narrow, obs, period)
result = runner.run(metric='nse', method='differential_evolution',
                    max_iter=150, reach_id=8)

print(result['calibration'])   # {'nse': 0.76}
print(result['validation'])    # {'nse': 0.71, 'kge': 0.73, 'pbias': -4.1}

# Đánh giá định tính
ratings = project.Statistic.evaluate_performance(
    obs.loc[period.valid_start:],
    ...  # sim từ run validation
)
# {'nse': 'Very Good', 'pbias': 'Very Good', 'rsr': 'Good'}

# ── Bước 4: Phân tích bất định (GLUE) ────────────────────────
calib = SWATCalibration(project)
glue = calib.glue_analysis(
    param_ranges    = param_ranges_narrow,
    observed_series = obs.loc[period.calib_start:period.calib_end],
    n_samples       = 1000,
    threshold       = 0.65,   # NSE ≥ 0.65 = behavioral
    metric          = 'nse',
    reach_id        = 8
)
print(f"Behavioral: {glue['behavioral_ratio']:.1%}")  # 12.3%
```

---

## 8. Thứ tự triển khai và tiêu chí xác minh

```
Bước 1 — Fix lỗi blocking (không thể bỏ qua)
├── Implement CalibrationManager._backup_state/_restore_state/_align_series
│   Verify: iteration thất bại → TxtInOut khôi phục đúng trạng thái ban đầu
├── Fix SWATRun.run(): str → Path(txinout_path)
│   Verify: project.run() không crash với TypeError
└── Fix raise None trong mapping_output.py line 112
    Verify: đọc cột không tồn tại → KeyError rõ ràng thay vì TypeError

Bước 2 — Nối CalibrationManager vào SWATCalibration
├── Thay self._manager = None → self._manager = CalibrationManager(project)
├── Sửa objective() dùng đúng signature HRUManager.update_params()
│   Verify: optimize() chạy 1 iteration → trả về float, không crash

Bước 3 — Thêm ValidationRunner + PeriodConfig
├── Implement ValidationRunner.run()
│   Verify: calib_score và valid_score đều là float (không phải nan)
└── Verify: valid_score gần với calib_score (không bị overfit)

Bước 4 — Fix SWATSensitivity
├── Sửa API calls: project.update_parameters → project.HRU.update_params
├── Sửa API calls: project.output.read_reach → project.Output.read_rch
└── Thêm n_parallel parameter, dùng WorkingFolderManager
    Verify: OAT 50 simulations với n_parallel=4 nhanh hơn ~4x so với tuần tự

Bước 5 — Dọn dẹp
├── Xóa 3 lệnh print() debug trong statistics.py._nse()
├── Xóa 2 lệnh print() trong mapping_output.py.__read_all()
└── Fix read_sed() dùng đúng constant _SED_DEFAULT_COLS
```

---

## 9. Các quyết định thiết kế và đánh đổi

### Quyết định 1: Backup toàn bộ thư mục vs. chỉ backup file được sửa

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| **Backup toàn bộ (chọn)** | Đơn giản, nhất quán tuyệt đối | Tốn disk (~50MB/backup) |
| Backup file được sửa | Tiết kiệm disk | Phức tạp hơn, dễ bỏ sót file |

→ Chọn backup toàn bộ vì TxtInOut điển hình < 100MB và thời gian copy < 1 giây.

### Quyết định 2: Không thêm abstraction mới vào SWATProject

`SWATCalibration` và `SWATSensitivity` gọi API không tồn tại. Có 2 cách sửa:

| Phương án | Cách làm |
|-----------|---------|
| **A (chọn):** Sửa code gọi sai | Thay `project.update_parameters()` → `project.HRU.update_params()` trong calibration/sensitivity |
| B: Thêm alias vào SWATProject | Thêm `def update_parameters(self, params): return self.HRU.update_params(params)` |

→ Chọn A: ít code hơn, không tạo surface area mới trên SWATProject.

### Quyết định 3: Sensitivity analysis parallel ngay từ đầu

OAT và Morris là **embarrassingly parallel** — mỗi simulation hoàn toàn độc lập. Không có lý do chạy tuần tự. `WorkingFolderManager` đã có sẵn và được thiết kế cho đúng use case này.

### Quyết định 4: Không thêm database hay persistence layer

Kết quả hiệu chỉnh trả về Python dict/DataFrame. Người dùng tự quyết định lưu vào CSV/pickle/database. Thêm persistence sẽ tạo dependency không cần thiết.

---

## 10. Tài liệu tham khảo khoa học

- **Moriasi, D.N. et al. (2007).** Model evaluation guidelines for systematic quantification of accuracy in watershed simulations. *Transactions of the ASABE*, 50(3), 885–900. — Tiêu chuẩn đánh giá NSE, PBIAS, RSR.

- **Beven, K. & Binley, A. (1992).** The future of distributed models: Model calibration and uncertainty prediction. *Hydrological Processes*, 6(3), 279–298. — Phương pháp GLUE.

- **Morris, M.D. (1991).** Factorial sampling plans for preliminary computational experiments. *Technometrics*, 33(2), 161–174. — Phương pháp Morris sensitivity.

- **van Griensven, A. et al. (2006).** A global sensitivity analysis tool for the parameters of multi-variable catchment models. *Journal of Hydrology*, 324(1–4), 10–23. — Ứng dụng sensitivity analysis cho SWAT.

- **Arnold, J.G. et al. (1998).** Large area hydrologic modeling and assessment part I: Model development. *Journal of the American Water Resources Association*, 34(1), 73–89. — Mô hình SWAT gốc.
