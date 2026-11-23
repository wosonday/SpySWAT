# Điều phối nền với herdr-core và `agm` (`agmag`), quy tắc tin nhắn và đồng bộ GitNexus

Tài liệu bổ sung cho [AGENTS-TUTORIAL.md](AGENTS-TUTORIAL.md) (mục 2.2, 3.2, 3.3, 3.4, 3.6, 4.1–4.3) và [BOT-CEO.md](BOT-CEO.md) (khi tách nhiều BOT-CEO theo từng mảng). Nếu có mâu thuẫn, quy tắc riêng của dự án ưu tiên hơn.

**Quản lý phiên bản Git giao cho GitHub Copilot** (`AGENTS-TUTORIAL.md` §3.3.1, [docs/COPILOT-GIT.md](docs/COPILOT-GIT.md)). `agm` và lớp wrapper worktree lo sinh/theo dõi/xoay vòng phiên và đo token; BOT-CEO (hoặc Codex ở dự án 1 luồng) quản lý đầu việc và bàn giao nhánh + SHA cuối (sau Review và bước cập nhật docs của Hydrogen Medium) + kết quả kiểm. Copilot tích hợp, revert và dọn worktree/nhánh đã tích hợp trong phạm vi được cho phép. Với MATHY-AI, tuân theo `docs/harness/GIT_BOT.md`.

Phạm vi: (1) dùng **`agm` (`agmag` v0.4.0)** đứng trên `hc` (`herdr-core`) để chạy nền, giao việc, nhắn tin, khóa `BRANCHES.md` (`agm branch`), MCP server 7 tool (`agm mcp`), kiểm soát ngân sách/xoay vòng, và các template cho từng vai; (2) quy tắc tin nhắn & hộp thư; (3) đồng bộ GitNexus khi worktree nằm ở `.wt/` trong dự án. Xem chi tiết tính năng mới tại [docs/AGM-0.4.0-GUIDE.md](docs/AGM-0.4.0-GUIDE.md).

> **Mức tin cậy:**
> - **Đã xác minh từ mã nguồn & nghiên cứu của `agmag` (`v0.2.0`, 2026-11-18/19):** kiến trúc lệnh `agm` (`daemon`, `tui`, `spawn`, `send`, `inbox`, `reply`, `done`, `ask`, `manage`, `rotate`, `cleanup`, `budget`, `policy`, `hook`, `ps`, `ls`, `cost`, `quota`, `log`, `scan`, `link`), sự kiện `hc events --json` (gồm `created`, `restarted`, `status`, `turn`, `title`, `labels`, `size`, `foreground`, `finished`, `lost`, `removed`), biến môi trường `HC_TERMINAL_ID`, và việc terminal của HERDR app có hiện trong `hc`.
> - Các chỗ đánh dấu **[KIỂM]** là điểm cần thử lại trên máy thực tế khi cấu hình dự án mới (ví dụ: tên model slug chính xác của `Opus High` trong `agy models`, việc `hc send` vào phiên `agy` tương tác, khởi động lại máy với Task Scheduler / `systemd`).

---

## Phần 1. Kiến trúc `agm` + `hc` và tự động hóa nền

### 1.1. Phân chia trách nhiệm: `hc` (tay chân) vs `agm` (sổ sách & luật)

Thay vì viết script bash tự bắt `hc events --json`, tự đếm `jq` và tự xoay vòng thủ công, **`agm` đảm nhận toàn bộ lớp điều phối, sổ sách và an toàn**, còn `hc` là lớp chạy terminal bên dưới:

| Thành phần | Đảm nhận | Lệnh chính |
|---|---|---|
| **`hc` (`herdr-core`)** | Chạy nền terminal, đọc màn hình, gõ phím, phát luồng sự kiện `hc events --json`, đặt `HC_TERMINAL_ID` | `hc run`, `hc read`, `hc attach`, `hc ls`, `hc events`, `hc server start\|status` |
| **`agm` (`agmag` v0.4.0)** | Theo dõi `hc events`, đo token/hạn mức gói (Claude/Codex/OpenCode/`agy`), hộp thư người dùng, gửi tin có ghi sổ, khóa ghi `BRANCHES.md`, MCP server stdio (7 tool cho quản lý/duyệt), giới hạn `max_workers` và ngân sách, xoay vòng thợ OpenCode & bàn giao phiên Claude/Codex, bảo vệ không tự kill Claude/Codex | `agm daemon`, `agm tui`, `agm spawn`, `agm send`, `agm inbox`, `agm reply`, `agm done`, `agm branch`, `agm mcp`, `agm ask`, `agm manage`, `agm rotate`, `agm cleanup`, `agm budget`, `agm policy`, `agm hook` |
| **Wrapper worktree (tùy chọn)** | Tạo `git worktree`, kiểm tra `tier:` / `skills:` trong `.agents/tasks/<ID>.md`, chạy `gitnexus analyze`, rồi gọi `agm spawn`; tự nhặt `.agents/inbox/*.md` | `dispatch.sh` (hoặc PowerShell tương đương), `cleanup-wt.sh` |

**Phân biệt ngân sách:** Claude CEO phân bổ kinh phí; [Go Console](https://opencode.ai/console/go) là nguồn kiểm hạn mức Go và nơi xem Extra Usage/budget. `agm quota` đã đọc được hạn mức Go (5h/tuần/tháng, provider `opencode-go`) qua `opencode api GET /api/experimental/usage/limits`; `agm` đo token và thực thi các ngưỡng đã cấu hình, không thay CEO duyệt nguồn tính phí.

**Đo OpenCode theo nguồn tính phí:** `agm` lưu model OpenCode dạng `providerID/id` (vd `opencode-go/deepseek-v4-pro`, `nvidia-kimi/moonshotai/kimi-k3.1-pro`, `openai/gpt-6.1-sol`), nên `agm cost --by model` tách được Go, NVIDIA, Zen free và OpenAI chạy qua OpenCode; model mới không cần khai báo trước. Billing lấy theo model đã khai trong `providers.toml`, nếu không thì theo tiền tố provider (`[providers."opencode-go"] billing = "subscription"`); provider chưa khai (như NVIDIA) để là chưa rõ. Cột **USD** của `agm cost`/`agm tui` = token × giá API niêm yết của từng model (`assets/prices.toml`, ghi đè bằng `[models."<id>".price]`), tính cả gói tháng như *giá trị nếu dùng qua API* — **không phải hóa đơn**; tiền thực trả của model tính theo API nằm ở cột `billed (API)` của `agm cost --summary`. `≥ $x` nghĩa là còn token chưa biết giá.

**Routing v3.6:** `opencode-go/deepseek-v4.1-flash` cho fast/mid/explore tương tác; `opencode-go/deepseek-v4-pro` cho review/strong phù hợp sau qualification. NVIDIA nền chỉ đọc, không chặn merge; không tự thêm scheduler vào `agm`. Xem [hướng dẫn NVIDIA](docs/NVIDIA-BACKGROUND.md).

**Lưu ý cài đặt `agm`:** từ repo `agmag`, cài bằng `cargo install --path .` (để có `agm` / `agm.exe` trong `~/.cargo/bin`). Dữ liệu mặc định nằm tại `~/.agmag/` (`agm.db`, `providers.toml`; đổi bằng `AGM_HOME`).

### 1.2. Khởi chạy `agm daemon` và các nguồn sự kiện

`agm daemon` chạy nền một vòng lặp duy nhất (mặc định mỗi `10` giây + nhận luồng `hc events --json` theo thời gian thực):

```powershell
# Khởi động herdr-core (nếu chưa chạy) và agm daemon sống độc lập với cửa sổ hiện tại
hc server start
hc run --bg --no-parent --name agm-daemon agm daemon
hc read agm-daemon          # xem log hoạt động của daemon
```

Để quan sát trực quan trong một pane của HERDR:

```powershell
agm tui                     # hạn mức gói (% còn lại), terminal (model/effort/where/last msg), hộp thư; `view` chọn tối đa 3 bảng
```

Các sự kiện tự động lúc này được xử lý qua hai lớp gọn nhẹ:

| Nguồn sự kiện | Ai xử lý | Hành động |
|---|---|---|
| **Trạng thái terminal đổi** (`blocked`, `finished`, `status`, `turn`, `foreground`) | `agm daemon` (`hc events --json`) | Tự ghép terminal ↔ phiên, đẩy câu hỏi `blocked` vào `agm inbox`, kiểm ngân sách & kích hoạt xoay vòng |
| **Ngữ cảnh đầy (`ctx_warn`, `ctx_rotate`)** | `agm daemon` (`rotation::tick`) | OpenCode worker: yêu cầu ghi `.agents/log/<ID>.md` + commit, kiểm worktree sạch rồi kill cũ + spawn mới. Claude/Codex đã `agm manage`: yêu cầu ghi `.agents/handoff/` rồi mở phiên mới, **không bao giờ tự kill phiên cũ** |
| **Tệp tác vụ mới** trong `.agents/inbox/<ID>.md` | Wrapper `inbox-watch` (tùy chọn, §1.6) | Chuyển sang `.agents/tasks/<ID>.md`, tạo worktree, gọi `dispatch.sh` → `agm spawn` |
| **Nhánh vừa được tích hợp** | GitHub Copilot (hoặc hook `post-merge`) | Làm mới GitNexus (phần 3), chạy `cleanup-wt.sh` dọn worktree/nhánh đã merge |

### 1.3. Cấu hình: `~/.agmag/providers.toml`, `agm budget` và `.agents/bot.env`

Các ngưỡng vốn trước đây nằm rời rạc ở `bot.env` (như `MAX_WORKERS`, `MANAGER`, ngưỡng xoay vòng) nay chuyển sang **`~/.agmag/providers.toml`** để `agm daemon` và `agm spawn` trực tiếp thực thi:

```toml
# ~/.agmag/providers.toml (không chứa khóa API)
[providers.codex]
billing = "subscription"
[providers.claude]
billing = "subscription"
[providers.agy]
billing = "subscription"
[providers.openrouter]
billing = "api"
[providers.ollama]
billing = "api"

[models."gpt-6.1-sol"]
provider = "codex"
context_window = 475000

[models."claude-opus-5-5"]
provider = "claude"

[policy]
max_workers = 3                 # số thợ (agm.role=worker) tối đa cùng lúc; không vượt giới hạn gói model cloud
manager = "ceo-platform"        # ví dụ: CEO đầu mối; codex-mgr nếu điều phối 1 luồng; bỏ trống = chỉ vào inbox
ctx_warn = 50                   # % ngữ cảnh: cảnh báo vào hộp thư
ctx_rotate = 70                 # % ngữ cảnh: bắt đầu xoay vòng
handoff_timeout_min = 10
link_timeout_min = 5
stats_months = 4
```

Thiết lập ngưỡng kỹ thuật (ví dụ, chỉ áp dụng theo mức đã duyệt; `agm daemon` kiểm mỗi chu kỳ):

```powershell
agm budget set task:login-7 --soft 2000000 --hard 5000000                 # đơn vị token; không phải tiền hoặc % Go
agm budget set provider:codex:10080 --soft 80 --hard 95                   # cảnh báo % hạn mức tuần
```

`agm spawn` kiểm `max_workers` cho vai `worker` và trần `task:<ID>` theo token đã ghi nhận. `provider:` chỉ có giá trị khi `agm` có số liệu cho đúng nguồn/cửa sổ; ví dụ `provider:opencode-go:300` có giá trị khi daemon/`agm quota --refresh` đọc được hạn mức Go (dữ liệu stale được coi như chưa có). `[policy].manager` chỉ là một đích nhận cảnh báo, không phải bộ phân bổ nhiều lane. Xem [quy tắc kinh phí của CEO](AGENTS-TUTORIAL.md#311-điều-phối-kinh-phí-ai).

Còn `.agents/bot.env` trong từng dự án chỉ giữ phần Git/worktree cho wrapper:

```bash
# .agents/bot.env  (đưa vào git; không chứa bí mật)
PROJECT_DIR=/duong/dan/den/du-an
BASE_BRANCH=main
WT_DIR=.wt                  # worktree nằm trong dự án (hoặc ../<TEN-DU-AN>.wt)
MANAGER=ceo-platform        # terminal điều phối việc của lane này (codex-mgr nếu dự án 1 luồng)
RUNTIME_DIR=.agents/.runtime
RUNTIME_TTL_DAYS=7          # dọn tệp tạm cũ hơn số ngày này
GITNEXUS_SYNC=none          # none | main | worktree  (phần 3)
```

Thêm vào `.gitignore` của dự án:

```
.wt/
.agents/.runtime/
```

*(Lưu ý: nếu dùng `agm hook install` cho Claude Code, `agm` cũng tự đọc chính xác hạn mức 5h/7d và `%` ngữ cảnh vào `agm.db` mà không cần cấu hình tay.)*

### 1.4. Template cho agent (dùng `agm` để giao tiếp và báo cáo)

Template là **một tệp `.md`** trong thư mục template của hc: trên Windows `%APPDATA%\herdr-core\templates\`, nơi khác `~/.config/herdr-core/templates/` (ghi đè bằng biến `AGM_HC_TEMPLATES`). Kiểm lại bằng `hc templates`. Phần thân là chỉ dẫn mở đầu cho agent; `agm spawn` truyền nhiệm vụ vào cuối thân qua `hc run`. Trên Windows, `hc run <template>` có thể lỗi `cannot start "sh"` (hc chạy `command:` qua `sh -c`); `agm` tự dự phòng bằng cách đọc template và chạy thẳng `command:` (xem `.agents/decisions/hc-template-sh-windows.md`).

> **Quy tắc chung đưa vào `AGENTS.md` và `CLAUDE.md` của mọi dự án:**
> - Liên lạc giữa agent: `agm send <tên-terminal> --type GIAO|BÁO CÁO|LỖI|HỎI|CHẶN|ĐẠT|CHƯA ĐẠT --task <ID> "<nội dung ngắn>"`
> - Cần người dùng quyết định: `agm send user --type HỎI --task <ID> "<câu hỏi>"` (vào `agm inbox`)
> - Xem hộp thư (Codex quản lý): `agm inbox --json`
> - Không dùng `agm kill` với phiên Codex/Claude — chỉ người dùng được làm việc đó.

**1) `worker-fast.md` / `worker-mid.md` / `worker-strong.md` (thợ cơ khí, OpenCode):**

*(Ba template dùng cùng phần thân: **`worker-fast/mid`** ưu tiên `opencode-go/deepseek-v4.1-flash`; **`worker-strong`** ưu tiên `opencode-go/deepseek-v4-pro` cho việc đã qualification, Codex ca khó theo CEO. Fast → mid cùng Flash không là nâng năng lực. `command: opencode` chỉ mở TUI, **không khóa model**; phải chọn/kiểm model thực trước giao việc. Với `opencode run`, truyền `--model` tường minh, kiểm quyền/mức cấp và cách nhận brief/báo cáo trước khi bật. `agm spawn --cwd` đã đặt worktree.)*

```markdown
---
description: Thợ cơ khí. Làm đúng một đầu việc trong một worktree.
command: opencode
ready: quiet
---
Bạn là thợ cơ khí. Làm theo thứ tự:
1. Đọc AGENTS.md ở gốc repo, rồi `.agents/tasks/<ID>.md` (ID nằm trong nhiệm vụ bên dưới).
2. Chỉ nạp và dùng các skill ghi ở trường `skills:` của tệp tác vụ (tối đa 2). Không tự thêm skill khác.
3. Chỉ sửa trong phạm vi tệp tác vụ cho phép. Không sinh agent khác. Tuyệt đối KHÔNG sửa tệp cấu hình lint (`eslint.config.*`, `.eslintrc*`) và KHÔNG thêm `eslint-disable`, `@ts-ignore`, `@ts-nocheck` hay `: any` để lách lỗi (CI sẽ chặn cứng).
4. Trước mỗi commit: chạy cổng lint nghiêm ngặt (`npx eslint . --max-warnings 0 --report-unused-disable-directives`, hoặc `ruff check` / `cargo clippy -- -D warnings`) + test trong tệp tác vụ; còn lỗi hoặc warning thì tự sửa cho bằng hết.
5. Mỗi bước nhỏ: ghi mục vào `.agents/log/<ID>.md`, rồi commit (thông điệp bắt đầu bằng `<ID>:`).
6. Tin nhắn gửi đi chỉ 1–3 dòng và trỏ tới tệp; luôn dùng `agm send` (không gửi nội dung dài).
7. Khi xong hoặc bị chặn: chạy lệnh `agm send` đã nêu trong nhiệm vụ (hoặc `agm send user --type HỎI` nếu cần người dùng quyết), rồi dừng.
```

**2) `auditor.md` (Audit & cổng chặn ESLint/CI — chạy model nhẹ / miễn phí):**

```markdown
---
description: Audit & cổng chặn ESLint/CI. Chạy test/build/lint và kiểm tra lách rule trên git diff (model miễn phí). Không sửa mã.
command: opencode
ready: quiet
---
Bạn là Audit. Không sửa mã nguồn. Chỉ dùng tối đa 1 skill ghi trong tệp tác vụ (nếu có).
Chạy các lệnh kiểm trong `.agents/tasks/<ID>.md`, chạy `git status`, `git diff --stat` và bắt buộc kiểm tra 3 cổng sau:
1. Phạm vi & nhật ký: tệp đổi nằm hoàn toàn trong phạm vi cho phép, khớp `.agents/log/<ID>.md`, và KHÔNG chạm tệp cấu hình lint (`eslint.config.*`, `.eslintrc*`) trừ khi tệp tác vụ cho phép.
2. Chặn lách rule trên diff: quét `git diff <nhánh-gốc>...HEAD` — nếu phát hiện dòng mới thêm `eslint-disable`, `@ts-ignore`, `@ts-nocheck` thì đánh CHƯA ĐẠT ngay lập tức.
3. Lint & Test: chạy `npx eslint . --max-warnings 0 --report-unused-disable-directives` (hoặc `ruff`/`clippy -D warnings`), typecheck và test đạt 100% (có test mới cho hành vi mới).
Ghi kết quả vào `.agents/log/<ID>.md` (một mục) và commit, rồi báo ĐẠT HẾT hoặc CHƯA ĐẠT cho quản lý bằng `agm send <MANAGER> --type BÁO CÁO --task <ID> "..."`.
```

**2b) `reviewer.md` (Reviewer mặc định qua OpenCode Go — tách khỏi hạn mức Claude Code & Codex):**

*(Ưu tiên **`opencode-go/deepseek-v4-pro`** sau qualification trong phần CEO cấp; Pro đã viết code thì đổi model khác họ đủ năng lực đã duyệt, như `agy` Argon/Hydrogen High còn hạn mức. Phiên mới độc lập, không đọc suy luận của thợ. Không dùng Codex mặc định. Khai báo `.opencode/agents/reviewer.md` chỉ đọc mã và chỉ ghi `.agents/reviews/`; kiểm model trước gửi brief, dùng GitNexus MCP nếu có.)*

```markdown
---
description: Reviewer mặc định qua OpenCode Go, chạy sau Audit và độc lập với worker.
command: opencode
ready: quiet
---
Bạn là Reviewer. Không sửa mã nguồn sản phẩm.
1. Đọc `.agents/tasks/<ID>.md`, `.agents/log/<ID>.md`, `git diff <nhánh-gốc>...HEAD` và (nếu có) kết quả phản biện trước của `agy` Opus High.
2. Nếu dự án có GitNexus MCP, chủ động gọi `detect_changes` và `impact` để kiểm phạm vi ảnh hưởng.
3. Ghi kết quả duyệt vào `.agents/reviews/<ID>-<n>.md` (ĐẠT hoặc CHƯA ĐẠT, lỗi theo mức Nghiêm trọng/Lớn/Nhỏ kèm tệp:dòng và cách sửa) và commit trên nhánh.
4. Báo quản lý (`codex-mgr` hoặc `ceo-<lane>`) bằng `agm send <MANAGER> --type ĐẠT|CHƯA ĐẠT --task <ID> "xem .agents/reviews/<ID>-<n>.md"`.
```

**3) `researcher.md` (Tìm kiếm/research — ưu tiên dùng `agm ask` một lần):**

- Với hỏi/tra cứu một lần (chỉ đọc), **ưu tiên gọi thẳng `agm ask`** thay vì mở terminal tương tác, vì `agm ask` tự chạy `agy --mode plan --sandbox` trong thư mục tạm ngoài repo, ghi đầy đủ token vào `agm.db` và không bị đếm trùng:
  ```powershell
  agm ask --model gemini-4-argon-medium --timeout 300 "<câu hỏi>. Mỗi kết luận kèm URL nguồn. Không sửa tệp."
  ```
- Nếu vẫn cần mở phiên `agy` trong `hc` (`hc run` / `agm spawn --role research`):
  ```markdown
  ---
  description: Tìm kiếm/research. Chỉ đọc. Mọi kết luận kèm URL nguồn.
  command: agy --model gemini-4-argon-medium --mode plan --sandbox
  ready: quiet
  ---
  Bạn là agent Tìm kiếm. Không sửa, không tạo tệp. Dùng search_web cho thông tin ngoài repo.
  Trả lời dạng danh sách: kết luận — URL nguồn (hoặc tệp:dòng). Con số, phiên bản, giá: trích nguyên văn từ nguồn.
  Không chắc thì ghi "chưa xác minh". Xong thì báo quản lý bằng `agm send`, rồi dừng.
  ```

**4) `sparring-opus.md` (Đồng Kiến trúc sư & Reviewer cấp cao — `agy` Opus High):**

- Dùng để **gánh tải trực tiếp cho Claude Code** ở hai việc tốn suy luận sâu nhất: **(a)** bàn thiết kế / chia `.agents/tasks/<ID>.md` cùng người dùng hoặc BOT-CEO, và **(b)** phân xử review cho các nhánh khó / rủi ro cao (bỏ Pre-review trên nhánh thường để tránh đốt 2 lần model lớn).
- **Luôn mở dưới dạng phiên tương tác trong repo** (hoặc nối tiếp bằng `agy --conversation <id>`) để tận dụng **`cache_read_tokens`** và để `agy` tự đọc đúng tệp/dòng trong repo — **không** dùng `agm ask` one-shot cho Opus High (vì `agm ask` chạy ở thư mục tạm ngoài repo với `cache_read_tokens = 0` và bắt nhồi cả diff vào dòng lệnh).
- *(**[KIỂM]** lấy tên `<opus-high-slug>` chính xác từ lệnh `agy models` trên máy.)*
- Mở bằng `hc run --name sparring sparring-opus` hoặc `agm spawn sparring-opus --task <ID> --role sparring --cwd <worktree>`:
  ```markdown
  ---
  description: Đồng Kiến trúc sư & Reviewer cấp cao dùng Opus High qua agy (giữ phiên để ăn prompt cache).
  command: agy --model <opus-high-slug> --mode plan --sandbox
  ---
  Bạn là Đồng Kiến trúc sư & Reviewer cấp cao (chỉ đọc, không sửa mã nguồn).
  - Khi bàn thiết kế / chia việc: đọc mã qua GitNexus / tệp liên quan để phản biện phương án, chỉ ra rủi ro và đề xuất chia nhỏ `.agents/tasks/<ID>.md`.
  - Khi phân xử review ca khó: đọc `.agents/tasks/<ID>.md`, `.agents/log/<ID>.md`, `.agents/reviews/` và `git diff` để kết luận ĐẠT/CHƯA ĐẠT theo mức Nghiêm trọng/Lớn/Nhỏ.
  Báo lại cho quản lý bằng `agm send`.
  ```

**5) `docs-hydrogen.md` (Cập nhật docs & báo cáo cuối sau Reviewer, trước Copilot — Gemini 4 Hydrogen Medium):**

- Được gọi **sau khi nhánh đã qua Reviewer / chỉnh sửa xong và trước khi gọi GitHub Copilot** (giảm tải việc viết báo cáo cho Codex).

```markdown
---
description: Cập nhật tài liệu (docs) và tổng hợp báo cáo cuối sau bước Reviewer, trước khi gọi Copilot.
command: agy --model gemini-4-hydrogen-medium
---
Bạn là agent Cập nhật Tài liệu (Gemini 4 Hydrogen Medium).
1. Đọc `.agents/tasks/<ID>.md`, `.agents/log/<ID>.md`, `.agents/reviews/<ID>-*.md` và `git diff <nhánh-gốc>...HEAD`.
2. Cập nhật các tệp tài liệu (README, docs/*.md, hướng dẫn sử dụng/vận hành) bị ảnh hưởng bởi thay đổi của nhánh (nếu có). Không sửa code nghiệp vụ.
3. Tổng hợp ngắn gọn báo cáo cuối vào `.agents/reports/<ID>.md` (đã đổi gì, model/phiên làm, kết quả kiểm số đếm, kết luận review, docs đã cập nhật, vấn đề lớn gợi ý cho Argon).
4. Ghi một mục vào `.agents/log/<ID>.md` liệt kê các tệp docs/báo cáo đã cập nhật, rồi commit trên nhánh hiện tại (thông điệp bắt đầu bằng `<ID>: docs: ...`).
5. Báo lại cho quản lý bằng `agm send <MANAGER> --type BÁO CÁO --task <ID> "Đã cập nhật docs/report, SHA mới: <sha>"`, rồi dừng.
```

**6) `argon-advisor.md` (Cố vấn kỹ thuật & Tối ưu Harnessing — Gemini Argon):**

- Có 2 cách dùng:
  - **Cố vấn kỹ thuật / review mã nhanh (chỉ đọc):** chạy `agm ask --model gemini-4-argon-high ...` hoặc script theo nhóm mô-đun kiểu `tools/argon_review.py` trong `agmag`.
  - **Cập nhật & tối ưu harnessing sau phiên:** chạy trong worktree/nhánh riêng để cải thiện `AGENTS.md`, `CLAUDE.md`, `HARNESSING.md`, `.agents/`, template, skill dựa trên các vấn đề lớn của phiên trước:

```markdown
---
description: Cố vấn kỹ thuật & tối ưu harnessing (Gemini Argon).
command: agy --model gemini-4-argon-high
---
Bạn là Cố vấn kỹ thuật chuyên trách Harnessing (Gemini Argon).
1. Đọc báo cáo cuối (`.agents/reports/`), nhật ký (`.agents/log/`), kết quả duyệt (`.agents/reviews/`) và mục hộp thư/lỗi lặp lại của phiên vừa qua.
2. Chỉ sửa các tệp thuộc hệ thống harnessing (`AGENTS.md`, `CLAUDE.md`, `HARNESSING.md`, `.agents/decisions/`, template, skill, quy tắc cổng). Không sửa code nghiệp vụ của sản phẩm trừ khi có tệp tác vụ riêng.
3. Ghi rõ vấn đề lớn của phiên trước, thay đổi tối ưu và kỳ vọng cải thiện vào `.agents/decisions/<ID>.md`, commit trên nhánh riêng và báo cho quản lý/Kiến trúc sư qua `agm send`.
```

*(**[KIỂM]** trên máy thật: `agy` khi chạy tương tác đã tự báo OSC 7501 `antigravity` theo `p0-research.md`, nhưng `hc send` vào phiên `agy` đang mở vẫn cần thử nghiệm 1 lượt thật ở Phần 4; nếu `hc send` bị treo, thêm `ready: quiet` vào template hoặc truyền nhiệm vụ ngay trong tham số khi `agm spawn`.)*

**7) `gitnexus-sync.md` (Cập nhật chỉ mục GitNexus — OpenCode model miễn phí):**

- Ưu tiên script/hook chạy `gitnexus analyze --index-only`; chỉ dùng template này nếu cần agent kiểm hoặc báo cáo.
- Sinh khi cần làm mới chỉ mục đồ thị sau khi `copilot-git` merge vào nhánh chung, khi `staleness` báo `behind`/`diverged`, hoặc khi worktree đổi cấu trúc:
  `agm spawn gitnexus-sync --task <ID> --role index --cwd "$PROJECT_DIR" -- "Cập nhật chỉ mục sau merge"`

```markdown
---
description: Cập nhật chỉ mục GitNexus (--index-only). Chạy model miễn phí, không sửa code hay tệp harness.
command: opencode
ready: quiet
---
Bạn là agent Cập nhật GitNexus (`gitnexus-sync`). Không sửa mã nguồn sản phẩm, không sửa `AGENTS.md`, `CLAUDE.md` hay `BRANCHES.md`.
Làm theo đúng thứ tự:
1. Kiểm tra không có tiến trình `gitnexus analyze` nào khác đang chạy (dùng khóa `.agents/.runtime/locks/gitnexus` hoặc `flock`).
2. Chạy `gitnexus status` tại thư mục được giao. Nếu cần làm mới (hoặc sau khi merge), chạy:
   `gitnexus analyze --index-only`
   (tuyệt đối KHÔNG bỏ cờ `--index-only` để tránh ghi đè `AGENTS.md`/`CLAUDE.md`).
3. Kiểm tra `git status --short` xác nhận không làm bẩn các tệp trong repo. Nếu dự án dùng máy chủ MCP HTTP (`gitnexus mcp --http --port 3111`), kiểm tra server đang sống (hoặc chạy `opencode mcp list` / `opencode reload` nếu cần).
4. Ghi ngắn kết quả (`gitnexus status`, SHA đã lập chỉ mục) vào `.agents/log/<ID>.md` (nếu thuộc một đầu việc đang mở), rồi báo quản lý qua `agm send <MANAGER> --type BÁO CÁO|LỖI --task <ID> "..."` và dừng.
```

### 1.5. Script giao việc: `.agents/bot/dispatch.sh` (dùng `agm spawn`)

**NVIDIA không đi qua script worker dưới đây.** Giao phiên chỉ đọc có quyền tối thiểu, theo [NVIDIA-BACKGROUND.md](docs/NVIDIA-BACKGROUND.md). Task ID/model, phạm vi đọc, mức cấp, deadline và SHA/snapshot là thông tin brief, không là tham số `agm` mới. CEO điều phối thủ công tối đa 1 task NVIDIA trên cả nhóm alias; `max_workers` không bảo đảm trần cho mọi vai nền. Đầu ra trả điều phối, không tự ghi log/docs/code. Không chờ NVIDIA trước merge.

So với phiên bản cũ, `dispatch.sh` không còn phải dùng `jq` để đếm `hc ls` hay kiểm tra giới hạn thợ bằng tay — **`agm spawn` tự kiểm tra `max_workers` (chỉ đếm `--role worker`), ngân sách `task:<ID>`, gắn nhãn `agm.task`/`agm.role`, tên `w-<ID>-<số>`, `--bg --outlive-parent` và lưu vào `agm.db`**. Vì `agm spawn` chạy nền không chặn (`--bg`), có thể gọi `dispatch.sh` song song cho nhiều đầu việc độc lập đã duyệt nguồn/ngân sách; đoạn tạo worktree dùng khóa ngắn `.agents/.runtime/locks/wt` để tránh đụng `.git/worktrees` khi sinh đồng thời. Nếu `agm spawn` từ chối (ví dụ đã chạm `max_workers`), script tự dọn worktree vừa tạo để không để lại worktree mồ côi.

**Trước `dispatch.sh`:** CEO xác nhận nguồn/model và mức đã cấp. Ví dụ dưới đây không kiểm điều đó hoặc hạn mức Go; không dùng làm cổng tự động cho model tính phí. Với việc dùng Go hoặc nguồn tính phí, giữ bước phê duyệt thủ công trước khi giao hoặc sinh lại phiên, trừ khi đã có cơ chế được kiểm chứng chỉ mở model đã phê duyệt trong phần được cấp.

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../bot.env"
cd "$PROJECT_DIR"

ID="$1"; TPL="${2:-worker-mid}"; ROLE="${3:-worker}"
# Mã việc: chỉ a-z 0-9 - _ (để tên w-<ID>-<n> hợp lệ <= 32 ký tự với hc & agm)
[[ "$ID" =~ ^[a-z0-9][a-z0-9_-]{0,26}$ ]] || { echo "ID '$ID' không hợp lệ: chỉ a-z 0-9 - _, tối đa 27 ký tự" >&2; exit 4; }
TASK=".agents/tasks/$ID.md"
[ -f "$TASK" ] || { echo "thiếu $TASK" >&2; exit 1; }

# Bậc model (trường `tier:` trong tệp tác vụ) -> template tương ứng (nếu đang gọi vai worker)
if [ "$ROLE" = worker ]; then
  tier=$(sed -n 's/^tier:[[:space:]]*//p' "$TASK" | head -1)
  case "$tier" in
    nhanh)       TPL=worker-fast ;;
    vừa|vua)     TPL=worker-mid ;;
    mạnh|manh)   TPL=worker-strong ;;
  esac
fi

# Giới hạn skill của thợ: tối đa 2 (trường `skills:` trong tệp tác vụ)
skills=$(sed -n 's/^skills:[[:space:]]*//p' "$TASK" | head -1)
if [ "$ROLE" = worker ]; then
  n=$(printf '%s' "$skills" | tr ',' '\n' | sed '/^[[:space:]]*$/d' | wc -l)
  [ "$n" -le 2 ] || { echo "thợ tối đa 2 skill, hiện có $n" >&2; exit 3; }
fi

WT="$WT_DIR/$ID"
CREATED_WT=0
if [ ! -d "$WT" ]; then
  mkdir -p .agents/.runtime/locks
  for _ in $(seq 30); do mkdir .agents/.runtime/locks/wt 2>/dev/null && break; sleep 0.2; done
  trap 'rmdir .agents/.runtime/locks/wt 2>/dev/null || true' EXIT
  if [ ! -d "$WT" ]; then
    git worktree add "$WT" -b "feat/$ID" "$BASE_BRANCH"
    CREATED_WT=1
  fi
  rmdir .agents/.runtime/locks/wt 2>/dev/null || true
  if [ "$CREATED_WT" -eq 1 ] && [ "$GITNEXUS_SYNC" = worktree ]; then
    ( cd "$WT" && flock /tmp/gitnexus.lock gitnexus analyze --index-only )
  fi
fi

# Giao qua agm spawn: tự kiểm max_workers, ngân sách task:<ID>, gắn nhãn agm.task & agm.role
if ! agm spawn "$TPL" --task "$ID" --role "$ROLE" --cwd "$PROJECT_DIR/$WT" -- \
  "Việc: $ID. Skill: ${skills:-không}. Khi xong hoặc bị chặn, chạy: agm send $MANAGER --type BÁO CÁO --task $ID \"xong, xem .agents/log/$ID.md\""; then
  if [ "$CREATED_WT" -eq 1 ]; then
    [ "$GITNEXUS_SYNC" = worktree ] && ( cd "$WT" && gitnexus clean ) || true
    git worktree remove --force "$WT" || true
    git branch -D "feat/$ID" || true
  fi
  exit 2
fi
```

**Gợi ý trên Windows (PowerShell):** vì `agm.exe` và `hc.exe` chạy gốc trên Windows 11, bạn có thể bỏ qua bước bash/flock và viết cùng logic tạo worktree + gọi `agm spawn` bằng một hàm PowerShell ngắn (không cần cài `jq` vì `agm spawn` đã tự kiểm tra số thợ và ngân sách trong SQLite).

### 1.6. Theo dõi & nhặt hộp thư đầu việc (`.agents/inbox/`)

- **Theo dõi terminal, câu hỏi `blocked`, ngân sách, xoay vòng:** đã có **`agm daemon`** chạy nền (§1.2) — **không cần `watch.sh` đọc `hc events --json` nữa**.
- Ví dụ dưới đây **không tự xét quyền chi phí**. Chỉ bật cho hàng đợi riêng đã duyệt trước và đã kiểm các template đều khóa ở model miễn phí/cục bộ; không đưa việc Go hoặc tính phí vào hàng đợi mẫu này. Chỉ xóa mục **sau khi `dispatch.sh` chạy thành công**; việc bị chặn vì hạn mức hoặc quyền chi phí chờ CEO, không thử lặp bằng watcher:

  Với mặc định fast/mid mới dùng Go, **không bật watcher mẫu nguyên trạng**. Không đưa NVIDIA vào watcher hoặc tự tạo lại task timeout; deadline task khác timeout một HTTP request (`settings.timeout`). OpenCode có retry transport sẵn; không chồng vòng retry ngoài. `429` thì dừng giao thêm và kiểm `Retry-After`/reset, không xoay alias.

```bash
#!/usr/bin/env bash
# .agents/bot/inbox-watch.sh (tùy chọn; chỉ chuyển inbox -> dispatch.sh khi spawn thành công)
set -euo pipefail
source "$(dirname "$0")/../bot.env"
cd "$PROJECT_DIR"; mkdir -p "$RUNTIME_DIR" .agents/inbox .agents/tasks

while true; do
  pids=()
  for f in .agents/inbox/*.md; do
    [ -e "$f" ] || continue
    (
      id=$(basename "$f" .md)
      cp "$f" ".agents/tasks/$id.md"
      if .agents/bot/dispatch.sh "$id"; then
        rm -f "$f"
      else
        echo "$(date -Is) dispatch $id lỗi/xếp hàng (giữ lại trong inbox)" >> "$RUNTIME_DIR/bot.log"
      fi
    ) &
    pids+=($!)
  done
  for p in "${pids[@]:-}"; do [ -n "$p" ] && wait "$p" || true; done
  sleep 10
done
```

### 1.7. Chạy liên tục trên Windows 11 / Linux và nút dừng khẩn cấp

Core dừng khi máy khởi động lại, nên cần tự bật lại `hc server start` và `agm daemon`:

- **Trên Windows 11 (khuyên dùng với `agm.exe`):** tạo tác vụ **Task Scheduler** (trigger *At log on*) chạy:
  1. `hc server start`
  2. `hc run --bg --no-parent --name agm-daemon agm daemon`
  *(và script PowerShell nhặt `.agents/inbox` nếu dùng).*
- **Trên Linux:** dùng `systemd --user` với `ExecStartPre=hc server start` và `ExecStart=/usr/bin/env agm daemon`.
- **Nút dừng khẩn cấp và kiểm soát an toàn:**
  - `agm policy off` — tắt ngay mọi hành động tự động của `agm daemon` (ngân sách kill/ngắt, xoay vòng).
  - `agm kill <t>` — Agent/policy **chỉ dừng được OpenCode**; muốn dừng/ngắt Codex hoặc Claude Code, chỉ người dùng mới làm được (gõ `y` tại terminal).
  - `agm manage <t>` — bật quản lý xoay vòng cho phiên Claude Code / Codex mở tay (yêu cầu người dùng xác nhận; riêng Claude cần đã chạy `agm hook install` một lần).

### 1.8. Quan sát từ xa (Moshi / SSH + `agm tui`)

Nhờ xác minh ngày 2026-11-18 (`p0-research.md`): các terminal mở trong **HERDR app** đều hiện trong `hc` (`herdr.space`, `herdr.tab`, `where`), nên **`agm` quản lý, đo token và gửi tin được thống nhất trong một hệ thống**:

- Từ máy tính hoặc điện thoại (Moshi + SSH): chạy `agm tui` để xem bảng tổng hợp & trả lời hộp thư (`reply <#> <text>`), hoặc `agm inbox` / `agm reply <#> "..."` / `agm ps` / `hc read <t> --lines 100` / `hc attach <t>`.

---

## Phần 2. Tin nhắn, hộp thư và dọn dẹp

Nguyên tắc: **tin nhắn là tín hiệu tạm; nội dung bền nằm trong tệp git**. `agm send` gọi `hc send --if idle` nên tin nhắn đi thẳng vào prompt agent đích và làm đầy ngữ cảnh người nhận; vì vậy tin phải thật ngắn, còn lịch sử gửi/nhận được `agm` lưu lại trong `~/.agmag/agm.db`.

### 2.1. Hai tầng lưu trữ

| Tầng | Nội dung | Nơi lưu | Vòng đời |
|---|---|---|---|
| **Bền** | Đặc tả, quyết định, tối ưu harness, mốc nhật ký, kết quả kiểm, kết quả duyệt, báo cáo cuối | `.agents/tasks/`, `log/`, `decisions/`, `reviews/`, `reports/` (đã commit) | Giữ cùng git |
| **Sổ máy & Tạm** | Tin `agm send`, hộp thư `agm inbox`, token/hạn mức, tệp bàn giao Claude/Codex | `~/.agmag/agm.db`, `.agents/handoff/` (nằm trong `git info/exclude`), `.agents/.runtime/` | `agm.db` giữ lịch sử đo; `.runtime/` dọn theo hạn |

### 2.2. Quy tắc cho người gửi (`agm send`)

1. Dùng đúng 7 loại tin mà `agm send` / `agm_send` chấp nhận: mã tiếng Anh `ASSIGN`, `REPORT`, `ERROR`, `QUESTION`, `BLOCKED`, `PASS`, `FAIL` hoặc mã tiếng Việt tương đương `GIAO`, `BÁO CÁO`, `LỖI`, `HỎI`, `CHẶN`, `ĐẠT`, `CHƯA ĐẠT` (CSDL lưu thống nhất theo mã Việt). Với `agm mcp`, chỉ gắn MCP server `agm` cho profile quản lý/duyệt (`BOT-CEO`, `Copilot`, `reviewer`), không gắn cho profile thợ (`worker-*`).
2. Mỗi tin **1 đến 3 dòng**, một việc, kèm đường dẫn tệp thay vì dán nội dung dài.
3. Nội dung đầy đủ phải đã nằm trong tệp bền (`.agents/tasks/`, `log/`, `reviews/`) **trước khi** gửi tin trỏ tới.
4. Cần người dùng trả lời hoặc xin quyết định → `agm send user --type HỎI --task <ID> "..."`. Không gửi tin tiến độ vụn ("đang đọc", "đang chạy"), vì trạng thái đã hiện trong `agm tui` / `agm ps` / `hc get`.

### 2.3. Quy tắc nâng lên bền (promote)

Trước khi một phiên bị xoay vòng hoặc kết thúc, mọi quyết định chọn hướng, lỗi nguyên văn + cách sửa, kết quả kiểm có số đếm, thay đổi phạm vi/model hoặc đề xuất tối ưu harness cho Argon phải được ghi vào tệp bền (`.agents/log/<ID>.md` hoặc `decisions/<ID>.md`) và commit. (`agm daemon` bắt buộc điều này với OpenCode worker: chỉ kill/thay phiên khi worktree sạch và có commit mới chạm `.agents/log/<ID>.md`.)

### 2.4. Dọn dẹp: phân biệt `agm cleanup` và dọn Git worktree

Có **hai loại dọn dẹp tách biệt** (không thay thế lẫn nhau):

1. **Dọn terminal cũ đã bàn giao trong `agm` / `hc`:**
   - Dùng `agm cleanup` (hoặc gõ `cleanup` trong `agm tui`). Chỉ **người dùng** chạy được và luôn hỏi xác nhận `y/N`. Lệnh này kết thúc/gỡ các terminal cũ đang ở trạng thái `[HANDED OFF]` sau khi phiên kế nhiệm đã chạy ổn, nhưng **luôn giữ** lịch sử token/rotations trong `agm.db` và tệp `.agents/handoff/`.
   - Với các terminal đã kết thúc còn nằm trong `hc ls --all` không thuộc vòng xoay, có thể gỡ bằng `hc rm <t>` (không dùng cho terminal đang `working` hoặc `blocked`).
2. **Dọn git worktree, nhánh đã tích hợp và `.agents/.runtime/` (do GitHub Copilot phụ trách):**
   - Copilot chỉ xóa worktree/nhánh sau khi xác nhận nhánh đã tích hợp vào `BASE_BRANCH`, sạch sẽ và không còn phiên `agm ps` đang chạy trong thư mục đó:

```bash
#!/usr/bin/env bash
# .agents/bot/cleanup-wt.sh — chỉ dọn tệp tạm và worktree/nhánh ĐÃ tích hợp & sạch
set -euo pipefail
source "$(dirname "$0")/../bot.env"
cd "$PROJECT_DIR"

# 1) Tệp tạm cũ trong runtime
[ -d "$RUNTIME_DIR" ] && find "$RUNTIME_DIR" -type f -mtime +"${RUNTIME_TTL_DAYS:-7}" -delete

# 2) Worktree đã tích hợp và sạch -> gỡ bỏ
git worktree list --porcelain | awk '/^worktree /{print $2}' | grep "/$WT_DIR/" | while read -r wt; do
  br=$(git -C "$wt" rev-parse --abbrev-ref HEAD)
  git merge-base --is-ancestor "$br" "$BASE_BRANCH" || continue        # chưa tích hợp: giữ
  [ -z "$(git -C "$wt" status --porcelain)" ] || continue              # còn thay đổi chưa commit: giữ
  [ "$GITNEXUS_SYNC" = worktree ] && ( cd "$wt" && gitnexus clean ) || true
  git worktree remove "$wt"
  git branch -d "$br"                                                  # -d: từ chối nếu chưa merge
done
git worktree prune
```

Không bao giờ xóa `.agents/tasks|log|decisions|reviews|reports`.

---

## Phần 3. Đồng bộ GitNexus khi worktree nằm ở `.wt/`

### 3.1. Có cần đồng bộ không: tùy dự án

GitNexus lập chỉ mục theo cây làm việc. Chọn chính sách qua `GITNEXUS_SYNC` trong `.agents/bot.env`:

| Giá trị | Nghĩa | Khi nào dùng |
|---|---|---|
| `none` | Không dùng GitNexus cho thợ trên nhánh | Dự án nhỏ; việc cục bộ, ít chạm nhiều module; máy yếu bộ nhớ |
| `main` | Chỉ lập chỉ mục nhánh chung; làm mới sau mỗi lần tích hợp; thợ dùng chỉ mục này **chỉ để tra cứu** | Dự án vừa; thợ cần biết cấu trúc nhưng thay đổi nhỏ |
| `worktree` | Mỗi worktree có chỉ mục riêng, làm mới khi tạo và khi cấu trúc đổi | Dự án lớn, nhiều module liên quan; việc refactor, đổi tên, chạm giao diện chung; Reviewer cần `detect_changes` trên nhánh |

Gợi ý: chỉ sửa trong một tệp/module → `none` hoặc `main`; đổi tên/đổi chữ ký/tách module → `worktree` (có thể đặt riêng trong `tasks/<ID>.md`). Máy ít RAM → ưu tiên `main` và giữ `flock` để chỉ một lượt `analyze` chạy tại một thời điểm.

### 3.2. Vì `.wt/` nằm trong dự án

1. **Phải thêm `.wt/` và `.gitnexus/` vào `.gitignore`**, nếu không `git status` của nhánh chung sẽ thấy các worktree hoặc kho chỉ mục GitNexus là tệp chưa theo dõi.
2. **Chỉ mục của nhánh chung không được quét `.wt/`** (tạo `.gitnexusignore` theo cú pháp `.gitignore` để loại trừ `.wt/` nếu cần trước khi chạy `analyze --index-only` ở gốc).
3. Luôn dùng cờ **`--index-only`** (không cần cờ cũ `--skip-embeddings`, vì embeddings mặc định tắt).
4. Dặn agent ở gốc không đọc trực tiếp `.wt/`.

### 3.3. Khi nào làm mới chỉ mục (qua agent `gitnexus-sync` hoặc hook)

| Chính sách | Thời điểm | Cách chạy |
|---|---|---|
| `main` hoặc `worktree` | Sau khi Copilot tích hợp nhánh vào nhánh chung (`merged`/`deployed`) | Gọi `agm spawn gitnexus-sync --task <ID> --role index --cwd "$PROJECT_DIR"` (chạy `gitnexus analyze --index-only`) hoặc hook `post-merge` |
| `main` hoặc `worktree` | Khi `gitnexus status` / `staleness.status` báo `behind` hoặc `diverged` | Gọi `gitnexus-sync` làm mới trước khi BOT-CEO/Reviewer đọc `query`/`impact` |
| `worktree` | Khi tạo worktree (nếu `GITNEXUS_SYNC=worktree`, không dùng shared store) | `gitnexus analyze --index-only` trong `.wt/<ID>` (`dispatch.sh`) |
| `worktree` | Khi thợ đổi cấu trúc (thêm/xóa/đổi tên tệp, đổi chữ ký) rồi cần `impact` lại | Gọi `gitnexus-sync` với `--cwd "$PROJECT_DIR/.wt/<ID>"` |
| `worktree` | Khi gỡ worktree | `gitnexus clean` trong worktree đó (`cleanup-wt.sh`) |

Hook git `post-merge` mẫu (`.git/hooks/post-merge` — chỉ làm mới chỉ mục GitNexus; **không** tự gọi `cleanup-wt.sh` ở đây để tránh xóa worktree trước khi `copilot-git` chạy xong bước Audit hậu merge):

```bash
#!/usr/bin/env bash
source "$(git rev-parse --show-toplevel)/.agents/bot.env"
[ "$GITNEXUS_SYNC" = none ] && exit 0
cd "$PROJECT_DIR" && flock /tmp/gitnexus.lock gitnexus analyze --index-only
```

---

## Phần 4. Kiểm tra trước khi cho chạy nền

Làm theo thứ tự, ghi kết quả vào `.agents/decisions/bot-setup.md`:

1. `agm --version` (`agm 0.4.0`), `hc --version`, `hc templates` thấy đủ template cần dùng (`worker-fast/mid/strong`, `auditor`, `reviewer`, `researcher`, `sparring-opus`, `docs-hydrogen`, `argon-advisor`, `gitnexus-sync`). Kiểm thêm `agm cost --by source` và `agm quota` hoạt động đúng để theo dõi tỷ lệ chuyển token sang model miễn phí / OpenCode / `agy`.
2. `agm hook install` (nếu dùng Claude Code) và mở `hc run --bg --no-parent --name agm-daemon agm daemon`; mở `agm tui` kiểm tra thấy các phiên đang chạy, hạn mức gói và không báo lỗi cấu hình `providers.toml`.
3. Chạy thử `agm ask --model gemini-4-argon-medium "Trả lời OK"` và kiểm tra token hiện trong `agm cost --window today --by source`; kiểm tra tên slug của **Opus High** qua `agy models`.
4. Kiểm thử tương tác qua `hc`: mở một phiên thử **Hydrogen Medium** (`docs-hydrogen`) và **Gemini Argon** (`argon-advisor`) trong worktree thử nghiệm, kiểm tra `agm send` đẩy lệnh vào đúng prompt và commit đúng phạm vi.
5. Thử vòng thợ hoàn chỉnh với ID viết thường `test-1`: `dispatch.sh test-1` tạo worktree `.wt/test-1`, `agm spawn` sinh `w-test-1-1` (và `TEST-2` bị từ chối vì chữ hoa); thợ chạy `agm send user --type HỎI --task test-1 "test"` và bạn trả lời qua `agm reply`; thử ép `agm rotate` trên `w-test-1-1` xem cơ chế bàn giao `.agents/log/test-1.md` + commit hoạt động đúng.
6. GitHub Copilot tích hợp nhánh thử (sau Review + Hydrogen docs) rồi gọi `gitnexus-sync` (`agm spawn gitnexus-sync --task test-1 --role index`) kiểm tra `gitnexus analyze --index-only` không làm bẩn `AGENTS.md`/`CLAUDE.md`; sau đó dọn worktree/nhánh (`cleanup-wt.sh`) và thử `agm cleanup` dọn terminal đã bàn giao (nếu có).
7. Khởi động lại máy (hoặc khởi động lại `hc server`): kiểm tra Task Scheduler / `systemd` có bật lại `hc` và `agm daemon`, đồng thời `agm ps` ghi nhận lại trạng thái các terminal.
8. Trước khi cho Go chạy nền, kiểm đăng nhập và model trên đúng môi trường worker, làm một lượt thử đã được CEO duyệt và đối chiếu Go Console. Diễn tập ba ca: đủ hạn mức → chạy đúng `opencode-go/...`; Go hết/không rõ hạn mức → nguồn dự phòng đã duyệt đủ năng lực hoặc `blocked`; model ngoài gói chưa duyệt → không spawn, hỏi người dùng. Xác minh watcher/rotation không mở model ngoài phần đã duyệt. Không bật Extra Usage để thử.
9. Qualification riêng Flash worker và Pro Reviewer/worker; nếu Pro viết code phải chọn Reviewer khác họ. Với NVIDIA, thử từng vai chỉ đọc tuần tự sau kiểm cloud/phí/quota; diễn tập deadline, task cũ chưa kết thúc, `429` và đầu ra lệch SHA. Không coi kiểm tài liệu là nghiệm thu runtime.
10. Tại gốc bộ tài liệu này, chạy `python -B scripts/lint_harness.py` và `python -B -m unittest discover -s tests -v`; xem [HARNESS-LINT.md](docs/HARNESS-LINT.md). Kiểm lỗi phải trả exit code khác 0, không báo xanh khi bỏ qua file thiếu/hỏng.

## Nguồn tham khảo

- `agmag` (`agm` v0.4.0): https://github.com/wosonday/agmag/ (`README_vi.md`, `CHANGELOG.md`, `src/main.rs`, `src/actions.rs`, `src/policy.rs`, `src/rotation.rs`, `src/ask.rs`, `src/daemon.rs`, `assets/providers.default.toml`, `.agents/decisions/p0-research.md`, `tools/argon_review.py`)
- herdr-core (`hc`, template, OSC 7501, `hc events`): https://github.com/herdrdev/herdr-core ; https://github.com/herdrdev/herdr-core/blob/master/docs/commands.md ; https://github.com/herdrdev/herdr-core/blob/master/docs/templates.md ; https://herdr.dev/app
- GitNexus: https://github.com/abhigyanpatwari/GitNexus ; https://unpkg.com/gitnexus@latest/README.md
- git worktree: `git help worktree`
