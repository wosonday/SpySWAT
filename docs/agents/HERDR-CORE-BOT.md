# Bot chạy nền với herdr-core, quy tắc tin nhắn và đồng bộ GitNexus

Tài liệu bổ sung cho `AGENTS-TUTORIAL.md` (mục 3.2, 3.3, 3.6, 4.2, 4.3). Nếu có mâu thuẫn, quy tắc riêng của dự án ưu tiên hơn.

Phạm vi: (1) lệnh và cấu hình để herdr-core kích hoạt bot theo sự kiện, và cách các agent được hướng dẫn để nối với bot; (2) quy tắc lưu và dọn tin nhắn; (3) đồng bộ GitNexus khi worktree nằm ở `.wt/` trong dự án.

> **Mức tin cậy:** các lệnh `hc` dưới đây lấy từ tài liệu công khai của herdr-core. Các chỗ đánh dấu **[KIỂM]** là suy luận hoặc tài liệu chưa nói rõ, phải thử trên máy thật (`hc <lệnh> --help`) trước khi dùng cho bot chạy không người giám sát. Các chỗ đánh dấu **[ĐÃ KIỂM 2026-11-17]** đã chạy thật với hc 0.1.21 trên Windows 11 (xem `AGENTS-TUTORIAL.md` mục 4.2.1).

---

## Phần 1. Bot theo sự kiện với herdr-core

### 1.1. Những gì herdr-core cung cấp (đã xác minh từ tài liệu)

herdr-core có CLI là `hc`. Các lệnh dùng trong tài liệu này:

| Lệnh | Tác dụng |
|---|---|
| `hc run [--bg] [--name N] [--cwd D] [--label K=V] [--outlive-parent] <lệnh hoặc template> [nhiệm vụ]` | Chạy chương trình hoặc template. `--bg` không chờ. Tên phải duy nhất trong các terminal đang sống. **[ĐÃ KIỂM]** Tên chỉ gồm 1–32 ký tự `a-z 0-9 - _` (**không có chữ hoa**). Cờ thêm: `--rm` (gỡ ngay sau khi thoát, khi cha đang chờ đã nhận mã thoát), `--no-parent` (không gán cha), `--parent T`, `--no-notify` (không gõ ghi chú về nó vào cha), `--keep`, `--timeout S`. |
| `hc ls [--all] [--label K=V] [--json]` | Liệt kê terminal đang sống (`--all` gồm cả đã kết thúc). **[ĐÃ KIỂM]** Trả một đối tượng `{"hidden_finished": n, "terminals": [...]}`, không phải mảng; mặc định ra JSON khi đi qua đường ống. |
| `hc send [--if idle\|working] [--wait] <terminal> <văn bản>` | Dán văn bản vào terminal đích rồi nhấn Enter. |
| `hc read <terminal> [--lines N]` | Đọc màn hình và lịch sử, không cần attach. |
| `hc wait [<terminal>] [--children any\|all] [--output <chuỗi>] [--timeout S]` | Chờ chương trình/agent con, hoặc chờ đến khi đầu ra chứa chuỗi. |
| `hc events [--terminal T] [--children-of T] [--label K=V] [--json]` | Theo dõi thay đổi theo thời gian thực; khi qua đường ống, mỗi sự kiện một dòng JSON. **[ĐÃ KIỂM]** Dạng dòng: xem §1.6. |
| `hc get <terminal>` | Ảnh chụp trạng thái một terminal. |
| `hc attach <terminal>` | Tiếp quản terminal (Ctrl+\ để rời). |
| `hc kill <terminal>` | Kết thúc chương trình. |
| `hc rm <terminal>` | Gỡ một terminal đã kết thúc. **[ĐÃ KIỂM]** có trong `hc --help`. |
| `hc server start\|stop\|status\|restart` | Điều khiển core. **[ĐÃ KIỂM]** `status` trả JSON có `live`, `finished`, `uptime_ms`, `version`. |
| `hc templates` | Liệt kê template. |
| `hc --skill` | In tài liệu hướng dẫn dành cho agent (cách giao việc, chờ, báo cáo, dọn dẹp). |
| `hc machine add <ssh-host>` / `hc run --on <máy>` | Chạy trên máy từ xa qua SSH. |

Quy tắc hành vi cần nhớ:

1. **Agent con tự kết thúc khi agent cha kết thúc**, trừ khi dùng `--outlive-parent`. **[ĐÃ KIỂM]** `hc run` gọi từ trong một terminal tự gán `parent` là terminal đó, và `hc get` cho thấy `die_with_parent: true` theo mặc định.
2. **Trạng thái do chương trình tự báo** qua giao thức OSC 7501; core không đoán từ nội dung màn hình và không nhận diện hãng agent. Chương trình không báo thì không có trạng thái. Các trạng thái được nêu: `idle`, `working`, `done`, `blocked`, `error`.
3. Mọi agent chạy trong core vẫn chạy khi đóng cửa sổ, nhưng **dừng nếu máy khởi động lại hoặc core dừng**.
4. Cấu hình: `~/.config/herdr-core/config.toml`; template: `~/.config/herdr-core/templates/`.

**Đã kiểm [ĐÃ KIỂM 2026-11-17]:** có `hc server start`; Claude Code **tự báo trạng thái** (`reported: true`, `status: {app: "claude-code", state: "working", msg: ...}`); chương trình thường (`ping`, `pwsh`) không báo (`reported: false`, `status: null`); `hc templates` ban đầu rỗng.

**Đã kiểm [ĐÃ KIỂM 2026-11-18]:** ý nghĩa của `--rm` và `--no-parent` (bảng trên); dạng dòng JSON của sự kiện `created` và `finished` (§1.6); `hc wait --output` chỉ dành cho **chương trình**, không dành cho agent (theo `hc wait --help`).

**Chưa xác minh [KIỂM]:** `hc` có tự khởi động core khi gọi lần đầu không (lúc kiểm, core đã chạy sẵn); dạng `data` của sự kiện đổi trạng thái (chưa bắt được, vì chương trình thử không báo trạng thái); việc Codex, OpenCode có tự báo OSC 7501 hay không.

### 1.2. "Sự kiện" của bot gồm những gì

herdr-core **không có bộ lập lịch hay webhook riêng** (theo tài liệu tôi đọc). Sự kiện thực tế có hai loại, nên bot gồm hai phần ghép lại:

| Nguồn sự kiện | Cách bắt | Hành động của bot |
|---|---|---|
| **Tệp tác vụ mới** trong `.agents/inbox/` (do người dùng, Kiến trúc sư hoặc Codex thả vào) | Vòng lặp kiểm tra thư mục (hoặc `inotifywait`) | Tạo worktree, chạy thợ bằng template |
| **Trạng thái terminal đổi** (`done`, `blocked`, `error`) | `hc events --json` | Báo cho `codex-mgr` bằng `hc send` |
| **Nhánh vừa được tích hợp** | Hook git `post-merge` gọi script | Làm mới GitNexus (phần 3), dọn worktree |
| **Định kỳ** | `cron` hoặc `systemd timer` | Dọn dẹp (phần 2.4) |
| **Issue/webhook bên ngoài** | Một script riêng ghi tệp vào `.agents/inbox/` | Như dòng đầu (không bao gồm trong tài liệu này) |

Nhờ đó mọi nguồn đều quy về một việc: **thả một tệp tác vụ vào `.agents/inbox/<ID>.md`**.

### 1.3. Cấu hình theo dự án: `.agents/bot.env`

```bash
# .agents/bot.env  (đưa vào git; không chứa bí mật)
PROJECT_DIR=/duong/dan/den/du-an
BASE_BRANCH=main
WT_DIR=.wt                  # worktree nằm trong dự án
MAX_WORKERS=3               # số thợ tối đa cùng lúc; không vượt giới hạn đồng thời của gói model cloud đang dùng
MANAGER=codex-mgr           # tên terminal của Codex quản lý
RUNTIME_DIR=.agents/.runtime
RUNTIME_TTL_DAYS=7          # dọn tệp tạm cũ hơn số ngày này (ngưỡng kinh nghiệm)
GITNEXUS_SYNC=none          # none | main | worktree  (phần 3)
```

Thêm vào `.gitignore` của dự án:

```
.wt/
.agents/.runtime/
```

### 1.4. Template cho agent (agent được hướng dẫn và nối với bot ở đây)

Template là **một tệp `.md`** trong `~/.config/herdr-core/templates/`. Tên tệp là tên template. Phần đầu (giữa hai dòng `---`) là các trường dạng `khóa: giá trị` (không phải YAML đầy đủ, không đặt dấu nháy). Phần thân là chỉ dẫn mở đầu cho agent; core nối nhiệm vụ vào cuối thân, cách một dòng trống. Các trường dùng được: `command` (bắt buộc), `description`, `ready` (`quiet` nếu agent không báo OSC 7501), `submit`, `stop`, `paste_gap_ms`.

**`worker.md`** (thợ cơ khí, OpenCode):

```
---
description: Thợ cơ khí. Làm đúng một đầu việc trong một worktree.
command: opencode
ready: quiet
---
Bạn là thợ cơ khí. Làm theo thứ tự:
1. Chạy `hc --skill` một lần để biết cách báo cáo và dọn dẹp.
2. Đọc AGENTS.md ở gốc repo, rồi `.agents/tasks/<ID>.md` (ID nằm trong nhiệm vụ bên dưới).
3. Chỉ nạp và dùng các skill ghi ở trường `skills:` của tệp tác vụ (tối đa 2). Không tự thêm skill khác.
4. Chỉ sửa trong phạm vi tệp tác vụ cho phép. Không sinh agent khác.
5. Mỗi bước nhỏ: ghi mục vào `.agents/log/<ID>.md`, rồi commit (thông điệp bắt đầu bằng `<ID>:`).
6. Tin nhắn gửi đi chỉ một đến ba dòng và trỏ tới tệp; không dán nội dung dài.
7. Khi xong hoặc bị chặn: gửi đúng một tin cho quản lý bằng lệnh `hc send` đã nêu trong nhiệm vụ, rồi dừng.
```

**`auditor.md`** (Audit, chỉ chạy kiểm):

```
---
description: Audit. Chạy test/build/lint và đối chiếu nhật ký với git diff. Không sửa mã.
command: opencode
ready: quiet
---
Bạn là Audit. Không sửa mã nguồn. Chỉ dùng tối đa 1 skill ghi trong tệp tác vụ (nếu có). Chạy các lệnh kiểm trong tệp tác vụ, chạy `git status`,
`git diff --stat` và đối chiếu "Tệp đổi" trong nhật ký với diff thực.
Ghi kết quả vào `.agents/log/<ID>.md` (một mục), rồi báo ĐẠT HẾT hoặc CHƯA ĐẠT cho quản lý bằng `hc send`.
```

**`researcher.md`** (Tìm kiếm, chỉ đọc). Từ 2026-11-18 vai này dùng **model Google qua Antigravity CLI `agy`** (xem `AGENTS-TUTORIAL.md` mục 2.2):

```
---
description: Tìm kiếm/research. Chỉ đọc. Mọi kết luận kèm URL nguồn.
command: agy --model gemini-4-argon-medium --mode plan --sandbox
ready: quiet
---
Bạn là agent Tìm kiếm. Không sửa, không tạo tệp. Dùng search_web cho thông tin ngoài repo.
Trả lời dạng danh sách: kết luận — URL nguồn (hoặc đường dẫn tệp:dòng trong repo). Con số, phiên bản, giá: trích nguyên văn từ nguồn.
Không chắc thì ghi "chưa xác minh", không đoán. Xong thì gửi đúng một tin cho quản lý bằng `hc send`, rồi dừng.
```

- Tìm trong mã của repo (không cần web) vẫn có thể dùng OpenCode agent `explore` với model rẻ; tìm ngoài repo dùng `agy`.
- **[ĐÃ KIỂM 2026-11-18]** `agy --mode plan --sandbox --print-timeout 150s --output-format json -p "…"` chạy được không cần người
  (trả `{"status":"SUCCESS","response":…}`), nên bot cũng có thể gọi `agy` dạng một lần thay vì mở terminal tương tác.
  **[KIỂM]** `agy` ở chế độ tương tác có báo OSC 7501 không (nếu không, giữ `ready: quiet`); `agy` có `hc send` được không.
- `agy` **không** đọc `.opencode/agent/*.md`: chạy nó ở thư mục tạm ngoài repo, không trong worktree có mã chưa merge.
- Kết quả research của Gemini đã từng sai phiên bản dù có URL (2026-11-18): Codex/Kiến trúc sư đối chiếu trước khi dùng.

Ghi chú:

0. Tạo ba bản `worker-fast.md`, `worker-mid.md`, `worker-strong.md` (cùng phần thân với `worker.md`, khác `command` để chọn agent/model OpenCode theo bậc; nguồn model xem `AGENTS-TUTORIAL.md` mục 2.1).
1. Chọn model cho OpenCode bằng cách đặt tùy chọn vào giá trị `command` (ví dụ `command: opencode <tùy chọn model>`) hoặc dùng agent khai báo trong `.opencode/agents/`. **[KIỂM]** cờ chính xác của OpenCode bằng `opencode --help`. Lưu ý: repo MATHY-AI hiện khai báo agent ở `.opencode/agent/` (số ít) và chạy bằng `opencode run --agent mathy-<profile> --model openai/…` trên opencode **v2** (gói npm `@opencode/cli`, đã kiểm v2.3.2 ngày 2026-11-18; v2 không có cờ `--dir`, phải `cd` vào worktree). Đặt template theo đúng thư mục và cờ mà bản OpenCode đang dùng nhận ra.
2. Với Claude Code hoặc Codex làm thợ bậc Mạnh, tạo template riêng (`worker-strong.md`) với `command: codex` hoặc `command: claude`. Tài liệu core chỉ yêu cầu `command` là một lệnh agent tương tác đã cài.
3. `ready: quiet` dùng khi agent không báo OSC 7501: core chờ đầu ra lắng xuống thay vì chờ tín hiệu trạng thái.
4. Nếu muốn agent trong core biết cách giao việc/báo cáo cho nhau, cho nó đọc `hc --skill` (đã có trong bước 1 của template).

### 1.5. Script giao việc: `.agents/bot/dispatch.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../bot.env"
cd "$PROJECT_DIR"

ID="$1"; TPL="${2:-worker}"
# tên terminal w-<ID>: hc chỉ nhận 1-32 ký tự a-z 0-9 - _ (không chữ hoa)  [ĐÃ KIỂM]
[[ "$ID" =~ ^[a-z0-9][a-z0-9_-]{0,29}$ ]] || { echo "ID '$ID' không hợp lệ: chỉ a-z 0-9 - _, tối đa 30 ký tự" >&2; exit 4; }
TASK=".agents/tasks/$ID.md"
[ -f "$TASK" ] || { echo "thiếu $TASK" >&2; exit 1; }

# bậc model (trường `tier:` trong tệp tác vụ) -> template tương ứng
tier=$(sed -n 's/^tier:[[:space:]]*//p' "$TASK" | head -1)
case "$tier" in
  nhanh|fast)          TPL=worker-fast ;;
  vừa|vua|mid)         TPL=worker-mid ;;
  mạnh|manh|strong)    TPL=worker-strong ;;
esac

# giới hạn skill của thợ: tối đa 2 (trường `skills:` trong tệp tác vụ)
skills=$(sed -n 's/^skills:[[:space:]]*//p' "$TASK" | head -1)
n=$(printf '%s' "$skills" | tr ',' '\n' | sed '/^[[:space:]]*$/d' | wc -l)
[ "$n" -le 2 ] || { echo "thợ tối đa 2 skill, hiện có $n" >&2; exit 3; }

# giới hạn số thợ  [ĐÃ KIỂM: hc ls trả đối tượng {hidden_finished, terminals:[...]}, đếm .terminals]
live=$(hc ls --json --label role=worker | jq '.terminals | length')
[ "$live" -lt "$MAX_WORKERS" ] || { echo "đủ $MAX_WORKERS thợ, xếp hàng"; exit 2; }

WT="$WT_DIR/$ID"
git worktree add "$WT" -b "feat/$ID" "$BASE_BRANCH"

if [ "$GITNEXUS_SYNC" = worktree ]; then
  ( cd "$WT" && flock /tmp/gitnexus.lock gitnexus analyze )   # mỗi lần một lượt phân tích
fi

hc run --bg --name "w-$ID" --cwd "$PROJECT_DIR/$WT" \
  --label role=worker --label task="$ID" --outlive-parent \
  "$TPL" "Việc: $ID. Skill: ${skills:-không}. Khi xong hoặc bị chặn, chạy: hc send $MANAGER \"[BÁO CÁO] $ID xong, xem .agents/log/$ID.md\""
```

Điểm thiết kế:

1. `--outlive-parent` để thợ không chết khi bot khởi động lại.
2. `--label` cho phép lọc `hc ls` và `hc events` theo vai.
3. Nhiệm vụ truyền cho thợ có sẵn lệnh `hc send` báo cáo, theo mẫu tài liệu của herdr-core (agent được dặn báo lại bằng `hc send`).
4. Thợ không tự merge và không tự phát hành (mục 6 của tài liệu chính).

### 1.6. Script theo dõi: `.agents/bot/watch.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../bot.env"
cd "$PROJECT_DIR"; mkdir -p "$RUNTIME_DIR" .agents/inbox .agents/inbox/done

# Phần A: tệp tác vụ mới -> giao việc (kiểm tra mỗi 10 giây)
( while true; do
    for f in .agents/inbox/*.md; do
      [ -e "$f" ] || continue
      id=$(basename "$f" .md)
      mv "$f" ".agents/tasks/$id.md"
      .agents/bot/dispatch.sh "$id" worker || echo "$(date -Is) dispatch $id lỗi/xếp hàng" >> "$RUNTIME_DIR/bot.log"
    done
    sleep 10
  done ) &

# Phần B: trạng thái terminal đổi -> báo quản lý
# [ĐÃ KIỂM] dòng đầu là ảnh chụp {"channel":..,"seq":..,"terminals":[..]} (không có .params.type -> bỏ qua);
# các dòng sau: {"jsonrpc":"2.0","method":"event","params":{"type":..,"terminal":"t12","seq":..,"data":{..}}}
hc events --json --label role=worker | while read -r line; do
  echo "$line" >> "$RUNTIME_DIR/events.jsonl"          # tạm thời, sẽ bị dọn (phần 2)
  type=$(jq -r '.params.type // empty' <<<"$line")
  term=$(jq -r '.params.terminal // empty' <<<"$line")
  case "$type" in
    finished)   # [ĐÃ KIỂM] data: {exit_code, finished_ms, reason: "exited"|"killed", signal}
      code=$(jq -r '.params.data.exit_code' <<<"$line")
      [ "$code" = 0 ] && msg="[BÁO CÁO] $term đã thoát (exit 0)" \
                      || msg="[CHẶN] $term thoát lỗi (exit $code). Xem: hc read $term --lines 50"
      hc send --if idle "$MANAGER" "$msg" ;;
    status)     # [KIỂM] dạng data; hc get cho status = {app, state, msg}, nên thử cả hai cách đọc
      st=$(jq -r '.params.data.status.state // .params.data.state // .params.data.status // empty' <<<"$line")
      case "$st" in
        blocked|error) hc send --if idle "$MANAGER" "[CHẶN] $term $st. Xem: hc read $term --lines 50" ;;
        done)          hc send --if idle "$MANAGER" "[BÁO CÁO] $term done" ;;
      esac ;;
  esac
done
```

Lưu ý: nếu bot (hoặc `codex-mgr`) là **cha** của thợ, `hc` đã tự gõ ghi chú `<hc>tN … exited …</hc>` vào cha khi thợ thoát. Khi đó hãy chạy thợ với `--no-notify` để cha không nhận hai lần cùng một tin, hoặc bỏ nhánh `finished` ở trên.

**Phương án dự phòng nếu agent không báo OSC 7501:** dùng chuỗi đánh dấu. Dặn thợ in một dòng như `[[DONE <ID>]]` khi xong, rồi để bot chạy `hc wait w-<ID> --output "[[DONE <ID>]]" --timeout 3600` (tùy chọn `--output` kết thúc khi đầu ra in **sau lúc bắt đầu chờ** có chứa chuỗi đó; trạng thái blocked, error hoặc thoát cũng làm nó kết thúc). **Cảnh báo [KIỂM]:** `hc wait --help` ghi `--output` là "for programs, not agents". Phải thử với thợ OpenCode thật trước khi dựa vào cách này. Nếu không được, phương án chắc chắn hơn là để thợ **thoát** khi xong, rồi bắt sự kiện `finished` (đã kiểm) hoặc dùng ghi chú tự động gửi về cha.

### 1.7. Chạy bot liên tục

Core dừng khi máy khởi động lại, nên cần dịch vụ khởi động cùng máy. Ví dụ `systemd` (người dùng):

```
# ~/.config/systemd/user/herdr-bot.service
[Unit]
Description=Bot herdr-core cho dự án

[Service]
ExecStart=/duong/dan/den/du-an/.agents/bot/watch.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

Bật bằng `systemctl --user enable --now herdr-bot`. Lệnh khởi động core là `hc server start` **[ĐÃ KIỂM: lệnh tồn tại]**; thêm `ExecStartPre=hc server start` để chắc core đã lên trước khi bot chạy. **[KIỂM]** `hc` có tự khởi động core khi gọi lần đầu không.

**Điều kiện cài đặt:** các script ở phần này cần `bash`, `jq`, `git`, `flock`. Máy kiểm 2026-11-18 (Windows 11, Git Bash) **không có `jq`**: cài bằng `winget install jqlang.jq`, hoặc viết lại phần đọc JSON bằng `ConvertFrom-Json` của PowerShell. Logic đọc sự kiện của `watch.sh` đã được thử bằng PowerShell trên sự kiện thật và cho kết quả đúng.

**Trên Windows** (không có `systemd`, `flock`, `inotifywait`): viết lại các script ở phần này bằng PowerShell và dùng Task Scheduler (trigger "At log on") để chạy `hc server start` rồi script theo dõi. Đây là đề xuất, chưa thử.

Giới hạn an toàn bắt buộc (theo mục 4.2 tài liệu chính): `MAX_WORKERS`, quyền `edit`/`bash` của OpenCode đặt rõ, chặn ghi ngoài worktree, có lệnh dừng khẩn cấp (`systemctl --user stop herdr-bot` rồi `hc kill` các thợ).

### 1.8. Điều khiển từ xa bằng Moshi

Với đội chạy trong core, người dùng kết nối SSH hoặc Moshi vào máy chủ rồi dùng `hc ls`, `hc read <terminal> --lines 100`, `hc attach <terminal>` (Ctrl+\ để rời), `hc send <terminal> "..."`. Có thể chọn hai mô hình, tùy anh/chị:

| Mô hình | Cách làm | Ưu | Nhược |
|---|---|---|---|
| **A. Cả đội trong core** | Chạy cả `codex-mgr`, Kiến trúc sư, Reviewer bằng `hc run --bg --name ...`; nhắn nhau bằng `hc send` | Một hệ thống duy nhất, không bị tách TUI/core | Không dùng giao diện TUI; herdr-mesh có thể không dùng được (nó bọc CLI `herdr`, **[KIỂM]**) |
| **B. TUI cho người, core cho bot** | Người ở TUI; bot ở core; bàn giao qua tệp (`.agents/inbox/`, `.agents/tasks/`, `.agents/log/`) và git | Giữ giao diện TUI | Hai bên không nhắn trực tiếp được; chậm hơn |

Khuyến nghị: thử mô hình A cho bot và thợ trước, vì `hc send`/`hc events`/`hc wait` đã đủ để nối agent với nhau mà không cần herdr-mesh.

---

## Phần 2. Tin nhắn: chỉ lưu phần quan trọng, phần còn lại dọn được

Nguyên tắc: **tin nhắn là tín hiệu tạm; nội dung bền nằm trong tệp git**. `hc send` dán văn bản thẳng vào prompt của agent đích, nên mỗi tin làm đầy ngữ cảnh của người nhận (suy luận của tôi); vì vậy tin phải ngắn.

### 2.1. Hai tầng

| Tầng | Nội dung | Nơi lưu | Vòng đời |
|---|---|---|---|
| **Bền** | Đặc tả, quyết định, mốc nhật ký, kết quả kiểm, kết quả duyệt, báo cáo cuối | `.agents/tasks/`, `log/`, `decisions/`, `reviews/`, `reports/` (đã commit) | Giữ cùng git |
| **Tạm** | Tin `hc send`, báo tiến độ, dòng sự kiện thô, đầu ra terminal | Terminal của core, `.agents/.runtime/` (không commit) | Dọn theo hạn |

### 2.2. Quy tắc cho người gửi

1. Mỗi tin **một đến ba dòng**, một việc, kèm đường dẫn tệp thay vì nội dung dài.
2. Tin loại `GIAO`, `LỖI`, `CHẶN`, `ĐẠT`, `CHƯA ĐẠT` chỉ là con trỏ; nội dung đầy đủ phải đã nằm trong tệp bền **trước khi gửi**.
3. Tin chỉ báo tiến độ ("đang làm", "đã đọc xong") **không gửi**; trạng thái đã có trong `hc get` và `hc events`.

### 2.3. Quy tắc nâng lên bền (promote)

Trước khi một tin hoặc đoạn đầu ra bị dọn, nếu nó chứa bất kỳ điều nào sau đây thì phải ghi vào tệp bền (nhật ký hoặc `decisions/`) và commit:

1. Một quyết định hoặc lý do chọn hướng.
2. Một lỗi (nguyên văn) và cách xử lý.
3. Kết quả kiểm có số đếm.
4. Một thay đổi phạm vi, model hoặc phiên.

Việc nâng lên do chính người nhận tin thực hiện (thợ ghi vào `log/`, Codex ghi vào `decisions/`), theo nguyên tắc mỗi tệp một người ghi.

### 2.4. Dọn dẹp: `.agents/bot/cleanup.sh`

Chạy định kỳ (`cron` hàng ngày) và sau mỗi lần tích hợp nhánh.

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../bot.env"
cd "$PROJECT_DIR"

# 1) Tệp tạm cũ (chỉ trong thư mục runtime, không động tới tệp đã commit)
find "$RUNTIME_DIR" -type f -mtime +"$RUNTIME_TTL_DAYS" -delete

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

3. **Terminal đã kết thúc trong core:** xem bằng `hc ls --all` (mỗi mục có `state: "finished"`, `exit_code`, `reason`); gỡ bằng `hc rm <terminal>` **[ĐÃ KIỂM: lệnh tồn tại]**. Ví dụ: `hc ls --all --json | jq -r '.terminals[] | select(.state=="finished") | .address' | xargs -r -n1 hc rm`. **[KIỂM]** ý nghĩa của `hc run --rm`. Không dọn terminal còn đang `working` hoặc `blocked`.
4. Lệnh dọn chỉ xóa thứ **đã tích hợp và đã commit** hoặc **nằm ngoài git**. Không bao giờ xóa `.agents/tasks|log|decisions|reviews|reports`.

---

## Phần 3. Đồng bộ GitNexus khi worktree nằm ở `.wt/`

### 3.1. Có cần đồng bộ không: tùy dự án

GitNexus lập chỉ mục theo cây làm việc. Tài liệu chính của GitNexus không nói rõ về git worktree; nó cho biết bỏ tham số `branch` thì truy vấn chỉ mục theo cây làm việc đang checkout, và chỉ mục có thể ghim theo nhánh bằng `--branch`. Vì vậy chính sách đồng bộ được chọn theo dự án, qua `GITNEXUS_SYNC` trong `bot.env`:

| Giá trị | Nghĩa | Khi nào dùng |
|---|---|---|
| `none` | Không dùng GitNexus cho thợ trên nhánh | Dự án nhỏ; việc cục bộ, ít chạm nhiều module; máy yếu bộ nhớ |
| `main` | Chỉ lập chỉ mục nhánh chung; làm mới sau mỗi lần tích hợp; thợ dùng chỉ mục này **chỉ để tra cứu** | Dự án vừa; thợ cần biết cấu trúc nhưng thay đổi nhỏ |
| `worktree` | Mỗi worktree có chỉ mục riêng, làm mới khi tạo và khi cấu trúc đổi | Dự án lớn, nhiều module liên quan; việc refactor, đổi tên, chạm giao diện chung; Reviewer cần `detect_changes` trên nhánh |

Gợi ý chọn nhanh:

1. Việc của thợ **chỉ sửa trong một tệp/module** và không đổi chữ ký hàm dùng chung → `none` hoặc `main` là đủ.
2. Việc **đổi tên, đổi chữ ký, tách/gộp module** → cần `worktree` cho riêng việc đó (có thể đặt cờ theo từng đầu việc trong `tasks/<ID>.md`: `gitnexus: worktree`).
3. Máy ít bộ nhớ hoặc có nhiều thợ → ưu tiên `main`, và chỉ cho một lượt `analyze` chạy mỗi lần (đã có `flock` trong `dispatch.sh`).

### 3.2. Vì `.wt/` nằm trong dự án

1. **Phải thêm `.wt/` vào `.gitignore`**, nếu không `git status` của nhánh chung sẽ thấy các worktree là thư mục chưa theo dõi.
2. **Chỉ mục của nhánh chung không được quét `.wt/`**, nếu không mỗi hàm sẽ xuất hiện nhiều bản (một bản mỗi worktree) và `impact` cho kết quả sai. **[KIỂM]** GitNexus có tôn trọng `.gitignore` khi lập chỉ mục không; nếu không, cấu hình loại trừ `.wt/` theo tài liệu của GitNexus trước khi chạy `analyze` ở gốc.
3. Thư mục lưu chỉ mục của GitNexus cũng không được commit. **[KIỂM]** tên thư mục thực tế sau khi chạy `gitnexus analyze` rồi thêm vào `.gitignore`.
4. Các công cụ tìm kiếm (grep, glob) của agent ở gốc dự án có thể đi vào `.wt/` và trả kết quả trùng lặp; `.gitignore` giúp các công cụ tôn trọng nó, còn lại dặn agent ở gốc không đọc `.wt/`.

### 3.3. Khi nào làm mới chỉ mục

| Chính sách | Thời điểm | Lệnh |
|---|---|---|
| `main` hoặc `worktree` | Sau khi tích hợp nhánh vào nhánh chung (hook `post-merge`) | `gitnexus analyze` ở gốc |
| `worktree` | Khi tạo worktree | `gitnexus analyze` trong `.wt/<ID>` (đã có trong `dispatch.sh`) |
| `worktree` | Khi thợ đổi cấu trúc (thêm/xóa/đổi tên tệp, đổi chữ ký) rồi cần `impact` lại | `gitnexus analyze` trong worktree đó |
| `worktree` | Khi gỡ worktree | `gitnexus clean` trong worktree đó (đã có trong `cleanup.sh`) |

OpenCode không có hook của GitNexus (chỉ có MCP và skill), nên **bot hoặc Codex làm mới chỉ mục thủ công** như bảng trên. Mỗi lần làm mới ghi một dòng vào nhật ký (`.agents/log/<ID>.md`), theo mục 3.3 tài liệu chính.

Hook git `post-merge` mẫu (`.git/hooks/post-merge`, có thể thực thi):

```bash
#!/usr/bin/env bash
source "$(git rev-parse --show-toplevel)/.agents/bot.env"
[ "$GITNEXUS_SYNC" = none ] && exit 0
cd "$PROJECT_DIR" && flock /tmp/gitnexus.lock gitnexus analyze
.agents/bot/cleanup.sh
```

---

## Phần 4. Kiểm tra trước khi cho chạy không người giám sát

Làm theo thứ tự, ghi kết quả vào `.agents/decisions/bot-setup.md`:

1. `hc --version`, `hc templates` thấy `worker-fast`, `worker-mid`, `worker-strong`, `auditor`, `researcher`. `hc --skill` in được tài liệu. (Lần kiểm 2026-11-17: `hc 0.1.21`, `hc templates` còn rỗng.)
2. `hc run --bg --name t-test opencode` rồi `hc get t-test`: xem agent có **báo trạng thái** không. Nếu `reported` là false, dùng `ready: quiet` và phương án chuỗi đánh dấu (mục 1.6).
3. `hc events --json | head -5` khi thay đổi trạng thái một terminal: **ghi lại hình dạng JSON thực tế** và sửa `jq` trong `watch.sh`. (2026-11-18: đã bắt được `created` và `finished`; còn thiếu sự kiện đổi trạng thái của một agent có báo, ví dụ Claude Code.)
4. Thả một tệp thử vào `.agents/inbox/test-1.md` (ID viết thường, vì tên terminal không nhận chữ hoa): có tạo `.wt/test-1`, nhánh `feat/test-1`, terminal `w-test-1` không. Thả thêm `TEST-2.md`: `dispatch.sh` phải từ chối với mã thoát 4.
5. Thợ thử gửi được `hc send codex-mgr` và tin đến đúng nơi.
6. Tích hợp nhánh thử rồi chạy `cleanup.sh`: worktree và nhánh được gỡ; các tệp `.agents/*` đã commit còn nguyên.
7. Nếu `GITNEXUS_SYNC=worktree`: chạy `gitnexus analyze` trong `.wt/TEST-1`, kiểm `impact` đúng nhánh; kiểm chỉ mục gốc không chứa bản sao từ `.wt/`.
8. Dừng dịch vụ bot, khởi động lại máy thử: bot và core có lên lại không, thợ đang chạy có sống không.

## Nguồn tham khảo

- herdr-core (`hc`, template, agent chạy agent, trạng thái OSC 7501, `--skill`, `hc events`): https://github.com/herdrdev/herdr-core ; https://github.com/herdrdev/herdr-core/blob/master/docs/commands.md ; https://github.com/herdrdev/herdr-core/blob/master/docs/templates.md ; https://github.com/herdrdev/herdr-core/blob/master/schema/README.md ; https://herdr.dev/app
- GitNexus (`analyze`, `clean`, phạm vi theo cây làm việc, `--branch`, hạn chế bộ nhớ, hook): https://github.com/abhigyanpatwari/GitNexus ; https://unpkg.com/gitnexus@latest/README.md
- git worktree (`git worktree add/remove/prune`): tài liệu git chính thức, `git help worktree`.
