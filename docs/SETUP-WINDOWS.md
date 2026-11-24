# Cài đặt đội agent nhiều model trên Windows (SpySWAT)

Bổ sung cho `../AGENTS-TUTORIAL.md` (phiên bản 3.6) và `../HERDR-CORE-BOT.md`. Tệp đó nói
**ai làm gì**; tệp này nói **mở các agent thế nào và theo dõi cuộc trò chuyện ở đâu**.
Các lệnh gốc đã được kiểm trên máy Windows 11 ngày 2026-11-18; phần bổ sung v3.4
(`agm`, `agy`, `copilot`, OpenCode Reviewer) ghi theo thực tế cài đặt trên máy ngày
2026-11-19 và đánh dấu rõ mục chưa chạy thử trên SpySWAT.

| Công cụ | Bản | Vai trong đội (v3.6) |
|---|---|---|
| Claude Code (`claude`) | 2.1.327 | Kiến trúc sư (**vai chính duy nhất mở Claude Code**; Reviewer chỉ khi leo thang rủi ro cao / 2 lần `CHƯA ĐẠT`) |
| Codex CLI (`codex`) | 0.169.0 | Quản lý (`codex-mgr`) |
| OpenCode (`opencode`) | 2.3.2 | Thợ (`worker-fast`/`worker-mid` → DeepSeek Flash Go, `worker-strong` → DeepSeek Pro Go), Tìm kiếm trong repo (`explore`, Flash Go), **Reviewer mặc định** (`reviewer`, `opencode-go/deepseek-v4-pro`); `auditor`/`gitnexus-sync` chạy script/CI |
| Antigravity CLI (`agy`) | đã cài | Tìm kiếm web (`gemini-3.8-flash` / `gemini-4-argon`), Đồng trao đổi (`Opus High` qua `agy`), Cập nhật docs (`gemini-4-hydrogen-medium`), Cố vấn & Tối ưu Harness (`gemini-4-argon-medium`/`high`) |
| GitHub Copilot CLI (`copilot`) | đã cài | Quản lý phiên bản Git (`copilot-git`, 1 phiên — merge đúng SHA, revert, dọn worktree/nhánh) |
| `agm` (`agmag`) | 0.1.0 (cài trên máy) | Điều phối trên `herdr-core`: `agm daemon`, `agm tui`, `agm spawn`, `agm send`, `agm inbox`, `agm ask`, `agm manage` (lưu ý `HERDR-CORE-BOT.md` viết cho `v0.2.0`) |
| herdr TUI (`herdr`) | 0.9.5 | Màn hình chung: mở, xem trạng thái, can thiệp |
| herdr-core (`hc`) | 0.1.21 | Nền chạy terminal & sự kiện cho `agm` |
| Ollama | 0.40.16, chưa có model | Dự phòng đã duyệt khi Go hết hạn mức; việc chạm dữ liệu thật chỉ chạy model cục bộ |

Mô hình khuyến nghị từ v3.4: **chạy thống nhất trong `herdr` / `herdr-core` (`hc`) kèm `agm`**,
hoặc mở từng pane thủ công trong `herdr` TUI nếu chưa bật `agm daemon`.
Mở `agm tui` trong một pane riêng để theo dõi hạn mức, % ngữ cảnh và hộp thư `agm inbox`.

---

## 1. Cài một lần

Chạy trong PowerShell, từ thư mục dự án `D:\SWAT-model\SpySWAT`.

### 1.1. Khởi động herdr và gắn tích hợp cho từng agent

```powershell
herdr                                  # lần đầu: onboarding, tạo session "default"
# trong herdr, mở một pane rồi chạy:
herdr integration install claude       # khôi phục phiên Claude khi herdr khởi động lại
herdr integration install codex        # báo trạng thái working/blocked/done của Codex
herdr integration install opencode     # plugin trạng thái cho OpenCode
herdr integration status               # kiểm: 3 dòng trên phải là "installed"
```

Tích hợp ghi hook/plugin vào thư mục cấu hình của từng agent (`~\.claude\hooks\`,
`~\.codex\`, `~\.config\opencode\plugins\`), nên mỗi người tự chạy trên máy mình.

### 1.2. Cài herdr-mesh (nhắn tin giữa agent)

herdr-mesh **không có trên npm registry**; cài từ GitHub:

```powershell
npm i -g https://github.com/runchr-works/herdr-mesh/archive/refs/heads/main.tar.gz
herdr-mesh install                     # tự đăng ký cho Claude Code, Codex, OpenCode
claude mcp list                        # phải thấy dòng herdr-mesh
```

Điều kiện: server herdr đang chạy (`herdr status` → `server: running`). Khởi động lại các agent
sau khi cài. Windows không được README nhắc tới: nếu `herdr-mesh install` lỗi, đăng ký tay
`claude mcp add -s user herdr-mesh herdr-mesh` và thêm `[mcp_servers.herdr-mesh]`
`command = "herdr-mesh"` vào `~\.codex\config.toml`.

### 1.3. Agent của OpenCode theo bậc model và quyền

`opencode models` trên máy này có các nhà cung cấp `anthropic`, `openai`, `openrouter`,
`huggingface`, `opencode`. Repo đã khai báo sẵn 7 tệp phân quyền trong `.opencode/agents/`
(`worker-fast`, `worker-mid`, `worker-strong`, `auditor`, `reviewer`, `explore`,
`gitnexus-sync`) với `permission` tách riêng (`edit`, `bash`, `task: deny`); bạn chỉ cần
bỏ chú thích dòng `model:` trong từng tệp theo mã chính xác lấy từ `opencode models` (hoặc
truyền `--model` khi gọi):

```markdown
<!-- .opencode/agents/reviewer.md (trích) -->
---
description: Default code reviewer (OpenCode). Read-only on product code; writes .agents/reviews/<ID>-<n>.md only.
mode: primary
# model: opencode-go/deepseek-v4-pro
permission:
  edit:
    "*": deny
    ".agents/reviews/*": allow
  task: deny
---
```

Gợi ý bậc theo v3.6 (bảng chuẩn: `OPENCODE-WORKERS-REVIEWER.md`; kiểm slug bằng `opencode models` và hạn mức Go trong Go Console trước khi giao):
`worker-fast`, `worker-mid`, `explore` → `opencode-go/deepseek-v4.1-flash`;
`worker-strong`, `reviewer` → `opencode-go/deepseek-v4-pro` (reviewer khác họ model nếu Pro viết code);
`auditor`, `gitnexus-sync` → script/CI (`pytest`, `git diff --check`); `:free`/Ollama chỉ là dự phòng đã duyệt;
NVIDIA (Kimi/Mistral/Nemotron) chỉ làm việc nền, chỉ đọc, không chặn merge (`NVIDIA-BACKGROUND.md`).
Việc chạm dữ liệu lưu vực thật chỉ dùng model cục bộ hoặc khi bạn đồng ý gửi lên cloud.

Trong giao diện OpenCode, phím `Tab` đổi agent (`worker-fast` / `worker-mid` / ...). Chạy
không giao diện: `opencode run --agent worker-mid "Việc: CAL-1"`.

---

## 2. Mở đội mỗi ngày

### 2.1. Bố cục trong herdr

```powershell
cd D:\SWAT-model\SpySWAT
herdr                                  # gắn lại session cũ nếu đã có
```

Phím: `Ctrl+b` thả ra rồi bấm phím lệnh. `v` chia phải, `-` chia dưới, `c` tab mới,
`q` rời (agent vẫn chạy), `?` xem mọi phím. Chuột dùng được: bấm pane, kéo viền, chuột phải.

| Workspace / tab | Pane | Lệnh | Tên agent |
|---|---|---|---|
| SpySWAT / `lead` | trái | `claude` rồi `/model` → Opus 5.5 (extra) hoặc Fable 5.2 (bật `agm manage arch`) | `arch` |
| SpySWAT / `lead` | phải | `codex` | `codex-mgr` |
| SpySWAT / `ops` | trên | `agm tui` (theo dõi hạn mức, % ngữ cảnh, hộp thư `agm inbox`) | — |
| SpySWAT / `ops` | dưới | `copilot` (chạy tại checkout tích hợp để merge đúng SHA) | `copilot-git` |
| SpySWAT / `review` | một pane | `opencode --agent reviewer` (mặc định; chỉ mở `claude` khi leo thang rủi ro cao / 2 lần `CHƯA ĐẠT`) | `review` |
| Mỗi đầu việc | một workspace riêng | `opencode` trong `.wt/<id>` (dùng ID viết thường cho `agm`/`hc`) | `w-<id>-<n>` |

Đặt tên để herdr-mesh và lệnh `herdr agent ...` gọi được:

```powershell
herdr agent list                       # xem mã và tên tự động
herdr agent rename <mã> codex-mgr
```

### 2.2. Mở thợ cho một đầu việc (mỗi việc một worktree)

```powershell
# 1. Codex (hoặc bạn) viết .agents/tasks/CAL-1.md theo .agents/templates/task.md
# 2. Tạo worktree + workspace riêng trong herdr:
herdr worktree create --cwd . --branch feat/CAL-1 --path .wt/CAL-1 --label CAL-1 --focus
# 3. Trong pane của workspace mới:
opencode                               # Tab → chọn worker-mid
# 4. Đặt tên:
herdr agent rename <mã> w-cal1-1
```

`.wt/` đã có trong `.gitignore`. Xong việc: `herdr worktree remove`, rồi `git branch -d feat/CAL-1`
sau khi đã merge.

---

## 3. Theo dõi các cuộc trò chuyện

Ba tầng, từ nhanh đến bền:

### 3.1. Đang diễn ra: herdr

- **Thanh bên:** trạng thái từng agent (`working` / `blocked` / `done` / `idle`) gộp theo
  workspace. `blocked` = agent đang chờ bạn trả lời.
- **Đọc mà không cần chuyển pane:**

```powershell
herdr agent list
herdr agent read codex-mgr --lines 80               # 80 dòng gần nhất
herdr agent wait w-cal1-1 --until done --until blocked   # chờ thay vì ngồi xem
herdr agent prompt codex-mgr "[BÁO CÁO] CAL-1 xong, xem .agents/log/CAL-1.md" --wait
```

- Khi chuyển tin giữa agent, dùng `herdr agent prompt` (hoặc công cụ `herdr_relay` của
  herdr-mesh): nó gõ và nhấn gửi trong một bước. Chỉ gửi khi agent đích không ở `working`.

### 3.2. Bền vững: tệp `.agents/` + git

Tin nhắn là con trỏ; nội dung nằm trong tệp đã commit (mục 3.3 của tutorial):

```powershell
git log --oneline -- .agents/                       # mọi đặc tả, nhật ký, duyệt, báo cáo
git log --oneline main..feat/CAL-1                  # một nhánh làm gì
Get-Content .agents/log/CAL-1.md                    # nhật ký của thợ
Get-ChildItem .agents/reviews/CAL-1-*.md            # các vòng duyệt
```

### 3.3. Lịch sử đầy đủ của từng công cụ

| Công cụ | Mở lại phiên | Danh sách / xuất | Nơi lưu |
|---|---|---|---|
| Claude Code | `claude -c` (phiên gần nhất), `claude --resume` (chọn) | trong `--resume` | `~\.claude\projects\<project-folder-slug>\*.jsonl` |
| Codex | `codex resume --last`, `codex resume <id>` | `codex resume` (bộ chọn) | `~\.codex\sessions\` |
| OpenCode | `opencode -c`, `opencode -s <id>` | `opencode session list`, `opencode session export <id>` | dịch vụ nền của OpenCode |

Các tệp lịch sử này nằm ngoài repo và có thể chứa dữ liệu riêng: không commit chúng
(repo công khai). Điều gì cần giữ lâu thì "nâng lên bền" vào `.agents/` (mục 2.3 của
`../HERDR-CORE-BOT.md`).

### 3.4. Từ xa (điện thoại / máy khác)

herdr giữ mọi pane khi bạn rời. Từ máy khác: `herdr --remote <máy-ssh>`; từ điện thoại: SSH
(Moshi) vào máy này rồi chạy `herdr`. Windows cần bật **OpenSSH Server** (Settings → System →
Optional features) trước.

---

## 4. Giai đoạn 2: điều phối nền với `agm` + `herdr-core` (`hc`)

`hc` (`0.1.21`), `agm` (`0.1.0`), `agy` và `copilot` đã cài trên máy, nhưng **chưa có template**
(`hc templates` rỗng). Theo v3.4 (`../HERDR-CORE-BOT.md`), `agm daemon` thay thế `watch.sh` để
theo dõi `hc events --json`, đo token, kiểm ngân sách, đẩy câu hỏi `blocked` vào `agm inbox`
và xoay vòng phiên. Trên Windows 11 dùng PowerShell và Task Scheduler (thay `systemd`). Làm
theo danh sách kiểm ở Phần 4 của `../HERDR-CORE-BOT.md` (lưu ý tệp đó tham chiếu
`agm v0.2.0`; cần đối chiếu lệnh của bản `0.1.0` đang cài bằng `agm --help`).

Lệnh hữu ích ngay cả khi chưa chạy tự động hoàn toàn: `hc ls`, `hc read <t>`,
`hc attach <t>` (`Ctrl+\` để rời), `hc wait <t>`, `agm tui`, `agm inbox`, `agm ask`.

---

## 5. Gỡ rối nhanh

| Triệu chứng | Lệnh |
|---|---|
| Agent không hiện hoặc sai trạng thái | `herdr agent list`, `herdr agent explain <mã> --json` |
| herdr-mesh không thấy agent | `herdr status` phải là `running`; agent phải cùng session herdr |
| Lệnh `herdr agent ...` báo không kết nối | Chưa mở `herdr` (server chưa chạy) |
| Dừng hết | `herdr server stop` (agent dừng theo) |
| Nhật ký herdr | `%APPDATA%\herdr\` |

Nguồn: `herdr --help`, `herdr agent|worktree|integration --help`, `hc --help`,
`opencode --help`, `codex resume --help` trên máy; https://herdr.dev/agent-guide.md;
https://github.com/runchr-works/herdr-mesh.
