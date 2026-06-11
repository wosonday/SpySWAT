# run_parallel_analysis.py
import pandas as pd
from spyswat import SWATProject
from spyswat.swat_calib.analysis import SWATCalibration, SWATSensitivity

# ══════════════════════════════════════════════════════════════
# BƯỚC 1 — Khởi tạo với n_parallel
# ══════════════════════════════════════════════════════════════
project = SWATProject(
    txinout_dir="my_swat_project/TxtInOut",
    working_dir="my_swat_project/workers",
    swat_exe="D:/SWAT/swat_rev688.exe",
    param_file="my_swat_project/params.txt",
    n_parallel=8          # ← số core bạn muốn dùng
)

# ══════════════════════════════════════════════════════════════
# BƯỚC 2 — Tải quan trắc và định nghĩa không gian tham số
# ══════════════════════════════════════════════════════════════
obs = pd.read_csv(
    "my_swat_project/observed_flow.csv",
    index_col="date", parse_dates=True
)["flow"]

param_ranges = {
    "CN2":      (35,   98),
    "ALPHA_BF": (0.0,  1.0),
    "GW_DELAY": (30,   450),
    "ESCO":     (0.01, 1.0),
    "SOL_AWC":  (0.01, 0.5),
}

# ══════════════════════════════════════════════════════════════
# BƯỚC 3 — Setup worker directories (1 lần duy nhất)
# ══════════════════════════════════════════════════════════════
# Tạo 8 bản sao TxtInOut trong thư mục workers/
# workers/TxInOut1/, workers/TxInOut2/, ..., workers/TxInOut8/
calib = SWATCalibration(project)
calib._manager.setup_parallel(overwrite=True)

# ══════════════════════════════════════════════════════════════
# BƯỚC 4 — Chạy GLUE song song: 1000 mẫu / 8 workers
# ══════════════════════════════════════════════════════════════
# Thời gian ≈ ceil(1000/8) × T_swat = 125 × T_swat
# Ví dụ: T_swat = 30s → tổng ≈ 63 phút (thay vì 500 phút tuần tự)
print("Đang chạy GLUE 1000 mẫu song song...")

glue_result = calib.glue_analysis(
    param_ranges=param_ranges,
    observed_series=obs,
    n_samples=1000,
    threshold=0.5,          # NSE ≥ 0.5 → behavioral
    metric="nse",
    output_variable="FLOW_OUTcms",
    reach_id=1
)

all_results   = glue_result["all_results"]        # DataFrame 1000 hàng
behavioral_df = glue_result["behavioral_results"] # NSE ≥ 0.5

print(f"Behavioral sets: {len(behavioral_df)}/1000 "
      f"({glue_result['behavioral_ratio']:.1%})")

# ── Xem phân bố NSE ─────────────────────────────────────────
print(all_results["nse"].describe())
#   count    1000.0
#   mean        0.48
#   max         0.74
#   ...

# ══════════════════════════════════════════════════════════════
# BƯỚC 5 — Best parameters & NSE tốt nhất
# ══════════════════════════════════════════════════════════════
best_idx    = all_results["nse"].idxmax()
best_row    = all_results.loc[best_idx]
best_score  = float(best_row["nse"])

best_params = {
    name: [(float(best_row[name]), "v")]
    for name in param_ranges
}

print(f"\nBest NSE = {best_score:.4f}")
print("Best parameters:")
for name, val in best_params.items():
    print(f"  {name:12s} = {val[0][0]:.4f}")

# ══════════════════════════════════════════════════════════════
# BƯỚC 6 — Kiểm định với best params
# ══════════════════════════════════════════════════════════════
# Áp best params vào TxtInOut gốc → chạy SWAT 1 lần
project.HRU.update_params(best_params)
project.run()

sim_best = project.Output.read_rch(
    columns=["RCH", "MON", "FLOW_OUTcms"],
    reach_id=1
)["FLOW_OUTcms"]

# Cắt giai đoạn kiểm định (ví dụ: 2010–2015)
obs_val = obs["2010-01-01":"2015-12-31"]
sim_val = sim_best["2010-01-01":"2015-12-31"]

stats_val  = project.Statistic.calculate_statistics(obs_val, sim_val)
rating_val = project.Statistic.evaluate_performance(obs_val, sim_val)

print(f"\nValidation:")
print(f"  NSE  = {stats_val['nse']:.3f}  → {rating_val['nse']}")
print(f"  KGE  = {stats_val['kge']:.3f}")
print(f"  PBIAS= {stats_val['pbias']:.1f}%  → {rating_val['pbias']}")

# ══════════════════════════════════════════════════════════════
# BƯỚC 7 — Sensitivity từ kết quả GLUE (0 SWAT runs thêm)
# ══════════════════════════════════════════════════════════════
sensitivity = project.Statistic.sensitivity_from_results(
    results_df=all_results,
    metric="nse",
    method="spearman"   # hoặc "prcc" cho kết quả chặt hơn
)

print("\nSensitivity ranking (Spearman):")
print(sensitivity[["parameter", "sensitivity_index", "rank"]].to_string(index=False))
# parameter  sensitivity_index  rank
# ALPHA_BF        0.83            1
# CN2             0.61            2
# GW_DELAY        0.45            3
# ESCO            0.31            4
# SOL_AWC         0.18            5

# ══════════════════════════════════════════════════════════════
# BƯỚC 8 (Tùy chọn) — Morris SALib nếu cần báo cáo học thuật
# ══════════════════════════════════════════════════════════════
sens = SWATSensitivity(project)

results_morris = sens.morris_salib(
    param_ranges=param_ranges,
    observed_series=obs,
    n_trajectories=20,   # 20 × (5+1) = 120 runs
    num_levels=4,
    metric="nse"
)

print("\nMorris (SALib):")
print(results_morris[["parameter","mu_star","sigma","ci_95"]].to_string(index=False))

# Vẽ biểu đồ
sens.plot_morris(
    results_morris,
    title="SWAT Sensitivity — Morris Method",
    save_path="morris_sensitivity.png"
)

# ══════════════════════════════════════════════════════════════
# BƯỚC 9 — Xuất kết quả tổng hợp ra CSV
# ══════════════════════════════════════════════════════════════
all_results.to_csv("glue_all_results.csv", index=False)
behavioral_df.to_csv("glue_behavioral.csv", index=False)

sens.export_results(
    results_morris=results_morris,
    save_path="sensitivity_results.csv"
)

print("\nHoàn tất. Các file đã xuất:")
print("  glue_all_results.csv    ← 1000 bộ tham số + NSE")
print("  glue_behavioral.csv     ← chỉ bộ tham số NSE ≥ 0.5")
print("  sensitivity_results.csv ← xếp hạng độ nhạy")
print("  morris_sensitivity.png  ← biểu đồ μ*–σ")