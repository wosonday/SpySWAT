# run_single.py
import pandas as pd
from spyswat import SWATProject

# ── 1. Khởi tạo project ─────────────────────────────────────────
project = SWATProject(
    txinout_dir="my_swat_project/TxtInOut",
    working_dir="my_swat_project/workers",
    swat_exe="D:/SWAT/swat_rev688.exe",
    param_file="my_swat_project/params.txt",
    n_parallel=1   # 1 luồng là đủ khi chỉ chạy 1 lần
)

# ── 2. Xem thông tin dự án ──────────────────────────────────────
project.info()
# TxtInOut: my_swat_project/TxtInOut
# HRUs: 45 | Subbasins: 12

# ── 3. Đọc giá trị tham số HIỆN TẠI trước khi thay đổi ─────────
current = project.read_params_values(["CN2", "ALPHA_BF", "ESCO"])
print(current)
#    param_name  hru_id  current_value
#    CN2         1       72.0
#    CN2         2       68.5
#    ALPHA_BF    1       0.048
#    ...

# ── 4. Thay thế tham số ─────────────────────────────────────────
# Format: {tên: [(giá_trị, phương_thức)]}
#   'v'   → gán trực tiếp:   CN2 = 75.0
#   'r'   → tương đối:       CN2 = CN2 × (1 + 0.1) → tăng 10%
#   'add' → cộng thêm:       CN2 = CN2 + 5.0

project.HRU.update_params({
    "CN2.mgt":      [(75.0,  "v")],    # gán trực tiếp = 75
    "ALPHA_BF": [(0.05,  "v")],    # gán = 0.05
    "ESCO":     [(0.1,   "r")],    # nhân với (1 + 0.1) → +10%
})

# ── 5. Chạy SWAT ────────────────────────────────────────────────
project.run()

# ── 6. Đọc kết quả ──────────────────────────────────────────────
sim = project.Output.read_rch(
    columns=["RCH", "MON", "FLOW_OUTcms"],
    reach_id=1
)["FLOW_OUTcms"]

print(f"Mean simulated flow: {sim.mean():.2f} m³/s")

# ── 7. So sánh với quan trắc ────────────────────────────────────
obs = pd.read_csv(
    "my_swat_project/observed_flow.csv",
    index_col="date", parse_dates=True
)["flow"]

stats  = project.Statistic.calculate_statistics(obs, sim)
rating = project.Statistic.evaluate_performance(obs, sim)

print(f"NSE  = {stats['nse']:.3f}  → {rating['nse']}")
print(f"KGE  = {stats['kge']:.3f}")
print(f"PBIAS= {stats['pbias']:.1f}%  → {rating['pbias']}")