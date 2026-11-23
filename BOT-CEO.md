# BOT-CEO — Điều phối đa mảng (lane) và kinh phí AI

Tài liệu bổ sung cho [AGENTS-TUTORIAL.md](AGENTS-TUTORIAL.md) (phiên bản 3.6) và [HERDR-CORE-BOT.md](HERDR-CORE-BOT.md). Lấy ý tưởng từ mô hình `HARNESSING.md` + `BRANCHES.md` của dự án `MATHY-AI` (`/mnt/d/Project/MATHY-AI/`), chuẩn hóa lại để dùng chung cho mọi dự án chạy cùng **`agm` (`agmag` v0.4.0)**, **`hc` (`herdr-core`)**, **Antigravity CLI (`agy`)** và **GitHub Copilot**.

> **Thứ tự ưu tiên tài liệu:** `AGENTS.md` / `CLAUDE.md` của dự án **>** `AGENTS-TUTORIAL.md` (quy tắc cứng & cổng phát hành) **>** `BOT-CEO.md` (mở rộng cơ chế đa lane & `BRANCHES.md`) **>** `HERDR-CORE-BOT.md` (hạ tầng `agm`/`hc`).

> **Quy tắc trao đổi với người dùng:** **1 lane = 1 BOT-CEO kiêm luôn vai Kiến trúc sư của lane đó** (không đặt thêm một Kiến trúc sư trung gian lên trên từng BOT-CEO). Khi cần trao đổi sâu, bạn **mở thẳng phiên BOT-CEO trong HERDR** và chat trực tiếp (gắn `agm manage <tên-terminal>` để tự xoay vòng ngữ cảnh); chỉ khi có thay đổi kiến trúc xương sống **liên mảng** mới chốt trước với 1 phiên Kiến trúc sư tổng (hoặc `agy` Opus High / Gemini Argon) rồi chia xuống từng lane.

> **Claude CEO chịu trách nhiệm điều phối kinh phí AI**, không phải duyệt thanh toán: phân bổ cho từng việc, chừa phần cho review/sửa lại, theo dõi hạn mức và dừng/đổi nguồn trong phạm vi đã duyệt. Nếu nhiều lane chia sẻ Go, chỉ định một CEO hiện có làm đầu mối để tránh cấp trùng phần còn lại. Xem [quy tắc ngân sách chung](AGENTS-TUTORIAL.md#311-điều-phối-kinh-phí-ai).
>
> **Routing v3.6:** `opencode-go/deepseek-v4.1-flash` cho worker-fast/mid và explore tương tác; `opencode-go/deepseek-v4-pro` cho Reviewer/strong phù hợp sau qualification. **NVIDIA nền chỉ đọc, không chặn merge**; một CEO hiện có điều phối tối đa 1 việc trên toàn nhóm alias, không mở thêm bot. Chi tiết ở [NVIDIA-BACKGROUND.md](docs/NVIDIA-BACKGROUND.md).

---

## 1. Vì sao phải tách thành nhiều BOT-CEO?

Trong dự án chỉ có 1–2 tính năng nhỏ, một phiên Kiến trúc sư + Codex quản lý là đủ. Nhưng khi dự án phình lớn với nhiều mảng nghiệp vụ khác nhau (ví dụ trong `MATHY-AI`: tồn kho/tạp hóa, thanh toán, chatbox, AI/RAG, nền tảng/DB), nếu dồn toàn bộ đề bài, lịch sử đọc mã, brief, log lỗi và kết quả test của mọi mảng vào **một agent điều phối duy nhất**, bạn sẽ gặp 3 vấn đề:

1. **Phình to ngữ cảnh (context bloat):** token tăng vọt, ngữ cảnh nhanh đầy (≥ 70%), chi tiết của mảng A làm nhiễu suy luận ở mảng B.
2. **Nghẽn hàng đợi tuần tự:** một phiên duy nhất không thể theo dõi sâu nhiều cụm worktree cùng lúc.
3. **Khó cô lập trách nhiệm:** khi có sự cố hoặc cần kiểm chứng lại, một phiên ôm quá nhiều nhánh dễ sót test hoặc nhầm phạm vi tệp.

**Giải pháp:** **một mảng (lane) = một BOT-CEO riêng** (mỗi BOT-CEO là một agent/terminal độc lập trong `herdr-core`). Mỗi BOT-CEO chỉ nạp và giữ ngữ cảnh của đúng mảng mình phụ trách, giao việc xuống worktree riêng, tự kiểm chứng nhánh của mảng mình, rồi đăng ký vào sổ hàng đợi chung **`BRANCHES.md`** để **một GitHub Copilot duy nhất** merge tuần tự.

---

## 2. Kiến trúc tổng thể nhiều BOT-CEO

```
                          Người dùng (chủ dự án)
             Giao mục tiêu · Đặt trần kinh phí · Duyệt phát hành
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
   BOT-CEO lane A            BOT-CEO lane B            BOT-CEO lane C
  (vd: ceo-tap-hoa)         (vd: ceo-chatbox)         (vd: ceo-platform)
   Claude / Codex            Claude / Codex            Claude / Codex
   Chỉ giữ ngữ cảnh A        Chỉ giữ ngữ cảnh B        Chỉ giữ ngữ cảnh C
          │                         │                         │
          ├──► Research: web agy · explore tương tác DeepSeek Flash Go · GitNexus chỉ đọc
          ├──► Đồng Kiến trúc sư (gánh tải cho Claude): phiên tương tác agy Opus High (giữ cache trong repo)
          ├──► Worktree nhánh riêng: agm spawn thẳng từ BOT-CEO (không qua codex-mgr trung gian)
           │                          (fast/mid DeepSeek Flash Go → Pro phù hợp / Codex ca khó)
          ├──► Audit & Pre-check: test/build/lint + kiểm diff & log (model miễn phí)
           ├──► Reviewer (1 tầng): DeepSeek Pro Go; khác họ nếu Pro đã viết code
          │                                       *(ca khó: agy Opus High / Codex; rủi ro cao -> Claude Opus High)*
          ├──► Cập nhật docs & báo cáo cuối (nếu cần): agy Gemini 4 Hydrogen Medium
          └──► NVIDIA nền: tổng hợp/đề xuất/log cho đợt sau, chỉ đọc, không chặn merge
                                    │
          ▼  Ghi BRANCHES.md qua `agm branch set` / `agm_branch_update` (khóa tự động, status: wip -> ready)
      BRANCHES.md  ◄── sổ đăng ký nhánh & điểm chạm mã giữa các lane
          │
          ▼  Đúng 1 phiên GitHub Copilot (copilot-git) đọc hàng đợi tuần tự
    Merge đúng head SHA -> Chạy lại Audit/Build -> Deploy (nếu được phép)
          │
          ▼  Làm mới đồ thị mã nguồn dùng chung cho các lane
    Cập nhật GitNexus (script analyze --index-only; agent :free nếu cần)
          │
          ▼  Tổng hợp vấn đề lớn giữa các lane / phiên
    Gemini Argon (agy): cập nhật & tối ưu hóa harnessing cho các phiên sau
```

### Nguyên tắc vàng để các BOT-CEO không dẫm chân lên nhau

1. **Cô lập ngữ cảnh:** BOT-CEO của lane A **không** đọc lịch sử chat hay code chi tiết của lane B; nó chỉ đọc trạng thái `wip`/`ready` và trường `touches_hotspot` / `depends_on` trong `BRANCHES.md`.
2. **Cô lập cây làm việc:**
   - Checkout chính (trên nhánh chung `main`): BOT-CEO **chỉ đọc mã** và **chỉ được ghi `BRANCHES.md` qua `agm branch set`**; chỉ `copilot-git` được merge/ghi mã vào checkout chính.
   - Worktree tách rời: đặt ngoài thư mục quét (hoặc trong `.wt/` đã thêm vào `.gitignore`), theo quy ước `<lane>--<slug>` (ví dụ `/mnt/d/Project/<repo>.wt/tap-hoa--low-stock`), nhánh `<lane>/<slug>`.
3. **Mỗi lane một nhóm tệp/điểm nóng ưu tiên:** gom các tính năng chạm cùng nhóm tệp vào **cùng một BOT-CEO** để nó tự xếp nối tiếp (`depends_on`), tránh hai lane sửa cùng một tệp rồi kẹt `needs-rebase`.

---

## 3. Phân vai khi áp dụng cùng `AGENTS-TUTORIAL.md` v3.6

| Vai trò | Công cụ / Model | Số lượng | Trách nhiệm chính | Không được làm |
|---|---|---|---|---|
| **BOT-CEO (theo lane)** | Claude Code (`claude-opus-5-5` / `claude-fable-5-2`) *(Codex nếu dự án có quy định riêng)* | 1 agent / lane (khuyến nghị ≤ 4–5 lane đồng thời) | Kiêm Kiến trúc sư và điều phối trực tiếp: phân bổ kinh phí, kiểm hạn mức, chia nhánh nhỏ (< ~400 dòng diff), giữ chỗ `wip`, gọi thẳng `agm spawn`, kiểm bằng chứng Audit/Review/Docs, đặt `ready` với SHA cố định | Tự tăng chi, sửa mã thay thợ (trừ 1 dòng kiểm chứng), merge, push `main`, deploy hoặc tự sửa quy tắc cứng |
| **Đồng Kiến trúc sư & Reviewer cấp cao** | **Opus High qua `agy`** (phiên tương tác trong repo / `--conversation <id>`, **không** dùng `agm ask` one-shot) | Theo đợt / lane | Bàn thiết kế & chia `.agents/tasks/<ID>.md` thay Claude Code khi cần bảo toàn hạn mức Claude (tận dụng `cache_read_tokens`); phân xử review cho các nhánh khó | Sửa tệp dự án; không gọi làm Pre-review thừa cho nhánh thường |
| **Reviewer (mặc định)** | **DeepSeek Pro Go** sau qualification; khác họ nếu Pro đã viết code, dự phòng `agy` đã duyệt; ca khó/rủi ro giữ thang leo cũ | Theo lượt duyệt, phiên mới | Duyệt độc lập 1 tầng trước docs / `ready`; không đọc lịch sử suy luận của thợ | Sửa code nghiệp vụ, tự duyệt cùng model đã viết |
| **Cập nhật docs & báo cáo** | **Gemini 4 Hydrogen Medium** (`agy`) | Theo nhánh có đổi docs/cần báo cáo | Nhận lệnh **sau khi Reviewer duyệt/chỉnh sửa xong, trước khi đặt `ready` gọi Copilot** để cập nhật docs + tổng hợp `.agents/reports/<ID>.md` và commit lên cùng nhánh | Sửa code nghiệp vụ, merge |
| **Audit & Thợ cơ khí** | Audit: **script/CI**; worker-fast/mid và explore tương tác: **Flash Go**; strong phù hợp: **Pro Go**, Codex ca khó; miễn phí/local đủ năng lực làm dự phòng | `[policy].max_workers` cho vai `worker` | Theo brief, qualification và mức cấp; code/test/log đúng phạm vi | Chạm `BRANCHES.md`, rời worktree, merge |
| **NVIDIA nền** | Kimi/Mistral/Nemotron theo [vai thử nghiệm](docs/NVIDIA-BACKGROUND.md) | Ban đầu tối đa 1 việc trên toàn nhóm alias, CEO kiểm thủ công | Tổng hợp cho đợt sau, đề xuất docs/log; trả kết quả kèm SHA/snapshot | Sửa tệp, duyệt nhánh, chặn merge, tự sinh agent hoặc né `429` bằng alias |
| **Bot GIT** | GitHub Copilot CLI (`copilot`) | **Đúng 1 phiên** (`copilot-git`) | Đọc `BRANCHES.md`, merge tuần tự đúng `head` SHA, chạy lại cổng kiểm tra, dọn worktree/nhánh đã merge | Tự sửa logic tính năng; bỏ qua `depends_on` hoặc cổng kiểm |
| **Cập nhật GitNexus (`gitnexus-sync`)** | Script/hook; `:free` / Ollama local nếu cần agent | Theo lượt (tối đa 1 lượt `analyze` mỗi lần) | Chạy `gitnexus analyze --index-only` tại checkout chính sau khi `copilot-git` merge (hoặc khi `staleness` báo cũ), giữ khóa tránh trùng và kiểm MCP server chỉ đọc | Sửa mã nguồn, sửa `AGENTS.md`/`CLAUDE.md`/`BRANCHES.md`, chạy `analyze` thiếu `--index-only` |
| **Cố vấn kỹ thuật & Tối ưu Harness** | **Gemini Argon** (`gemini-4-argon-*` qua `agy`) | 1 vai cố vấn liên lane | Cố vấn kỹ thuật giống Codex; **tổng hợp các vấn đề lớn từ các BOT-CEO sau mỗi đợt** để cập nhật và tối ưu hóa harnessing chung (`AGENTS.md`, `CLAUDE.md`, template, skill, `BRANCHES.md`) | Đụng vào luồng code đang chạy dở của từng lane |

---

## 4. Giao thức `BRANCHES.md` và khóa ghi song song

### 4.1. Cấu trúc một mục trong `BRANCHES.md`

Mỗi nhánh là một khối `### <lane>/<slug>` dùng cặp `- khóa: giá trị` để cả người và script/Copilot đều đọc được:

```markdown
### tap-hoa/low-stock
- status: ready
- lane: ceo-tap-hoa
- tier: vừa
- head: 9f8e7d6c5b4a      # SHA cuối (đã gồm commit docs của Hydrogen nếu có); Copilot merge ĐÚNG SHA này
- base: 1a2b3c4d5e6f      # SHA của main khi tách nhánh
- depends_on: -           # nhánh khác phải merged/deployed trước, cách nhau dấu phẩy
- migration: no           # yes nếu có migration DB
- touches_hotspot: -      # tệp dùng chung dễ đụng giữa các lane (vd: core/models.py)
- summary: Cảnh báo hàng sắp hết khi tồn dưới ngưỡng cấu hình
- verify: <lệnh test/build thực tế đã chạy và kết quả số đếm>
- review: opencode-go/deepseek-v4-pro, 0 bắt buộc sửa, .agents/reviews/tap-hoa--low-stock-1.md
- docs: gemini-4-hydrogen-medium (đã cập nhật docs/inventory.md) | không đổi
- registered: 2026-11-19T08:40+07:00
- git: -                  # copilot-git ghi: merge SHA, log, trạng thái deploy hoặc lý do lỗi
```

### 4.2. Bảng chuyển trạng thái

| Trạng thái | Ai đặt | Ý nghĩa & quy tắc |
|---|---|---|
| `wip` | BOT-CEO | **Giữ chỗ ngay khi bắt đầu chia việc** — để các BOT-CEO khác thấy vùng đang làm và tránh đụng tệp. `copilot-git` bỏ qua. |
| `blocked` | BOT-CEO | Chờ người dùng quyết định hoặc chờ nhánh thuộc lane khác (`depends_on`). |
| `ready` | BOT-CEO | Đã qua Audit + Reviewer + Hydrogen cập nhật docs + rebase lên `main` + chạy lại kiểm; `head` SHA cố định. **Cấm commit thêm sau khi đặt `ready`.** |
| `merging` | `copilot-git` | Đang tích hợp vào nhánh chung và chạy lại cổng kiểm. |
| `merged` / `deployed` | `copilot-git` | Đã vào `main` (và deploy xong nếu bật). Trạng thái cuối; Copilot dọn worktree/nhánh. |
| `needs-rebase` | `copilot-git` | Xung đột merge, SHA lệch hoặc >1 migration head → trả về đúng `lane` của BOT-CEO xử lý. |
| `failed` | `copilot-git` | Cổng kiểm sau merge hoặc deploy lỗi (kèm đường dẫn log) → trả về BOT-CEO giao lại thợ sửa. |

### 4.3. Ghi `BRANCHES.md` an toàn khi nhiều BOT-CEO và Copilot cùng ghi

Không tự khóa bằng tay. **Mọi thao tác ghi `BRANCHES.md` đi qua `agm`**, lệnh tự lấy khóa, sửa đúng một mục, ghi nguyên tử và nhả khóa:

```bash
# Ghi/cập nhật một mục (tạo mục nếu chưa có; BRANCHES.md phải tồn tại sẵn, dùng đường dẫn tuyệt đối)
agm branch set <lane>/<slug> status=wip lane=<lane> touches_hotspot=none   --file /abs/path/BRANCHES.md
# Chốt ready: cần --worktree để agm kiểm worktree sạch và HEAD khớp head đã khai
agm branch set <lane>/<slug> status=ready head=$HEAD_SHA verify="..." review="..."   --file /abs/path/BRANCHES.md --worktree /abs/path/worktree
# Đọc một mục
agm branch get <lane>/<slug> --file /abs/path/BRANCHES.md
```

Agent có MCP server `agm` dùng tool tương đương: `agm_branch_update` (ghi, `branches_file` là đường dẫn tuyệt đối) và `agm_branch_get` (đọc).

- Khóa là thư mục `.agents/.runtime/locks/branches` cạnh `BRANCHES.md` (nằm trong `.gitignore`); `agm` chỉ giữ nó vài mili-giây, chờ tối đa 30 giây và **thu hồi khóa cũ hơn 60 giây**.
- **Cấm `mkdir`/`rmdir` khóa bằng tay**: một lần giữ tay quá 60 giây có thể bị `agm` thu hồi và làm mất cập nhật của lane khác.
- Terminal vai trò `worker` bị `agm` từ chối ghi `BRANCHES.md`.
- Khuôn mục (§4.1) và bảng trạng thái (§4.2) giữ nguyên.

---

## 5. Vòng đời một đầu việc trong BOT-CEO (kết hợp `agm` + `hc`)

### 5.0. Trước khi chạy: Khung xác định mục tiêu kiểu Lauren Tan (`Goal first · Process second · Then routines`)

Khi mới mở một BOT-CEO (hoặc nhận một đề bài lớn mới cho lane), BOT-CEO **làm chủ mục tiêu cuối (`you own the goal, not the steps`)** và bắt buộc đi qua 6 bước làm rõ trước khi được phép `agm spawn` bất kỳ thợ nào (*"understand it first. automate it second"*):

1. **`01 / goal.first` — Chốt mục tiêu cuối & giá trị phục vụ:**
   - `/interview`: nếu đề bài còn mơ hồ, hỏi lại người dùng cho tới khi người dùng xác nhận *"Đúng, chính là nó"*.
   - `serves`: chỉ rõ đợt việc này phục vụ **`revenue`** (tính năng mới, tăng chuyển đổi/bán hàng) hay **`cost`** (giảm lãng phí token, giảm sửa lại `rework`, giảm giờ vận hành).
2. **`02 / process.dump` — Nhận bản nháp thô & tạm dừng (`hold`):**
   - Người dùng có thể đổ một bản mô tả thô/lộn xộn (voice dump / ghi chú). BOT-CEO tự gom đủ 6 mảnh:
     - `steps` (luồng thực hiện hiện tại), `watch_outs` (điểm nóng / bẫy cần coi chừng), `tools` (module, CLI, DB liên quan), `check_work` (lệnh test/lint nào chứng minh làm đúng), `info_from` (nguồn dữ liệu/tệp đầu vào), `feedback_from` (cổng Audit/Reviewer/người dùng nghiệm thu).
   - `/restate` + **`hold := do NOT execute yet`**: diễn đạt lại `goal + process` ngắn gọn, dễ hiểu rồi **dừng lại chờ xác nhận** — chưa sinh worktree hay `agm spawn` ở bước này.
3. **`03 / how.i.think` — Khai mở quyết định ẩn & định nghĩa `done`:**
   - `/ask one question at a time`: mỗi lượt chỉ hỏi **đúng 1 câu** về các quyết định ẩn (không hỏi dồn một danh sách dài).
   - `conflict`: khi hai nguồn mâu thuẫn (ví dụ tài liệu cũ vs code thật trên `main`), chốt rõ nguồn nào thắng.
   - `done`: **"Giao thợ / viết code xong" chưa phải là xong (`"sent" is not done`)** — chỉ tính là `done` khi:
     - `saved`: commit code + `.agents/log/<ID>.md` + test tồn tại và đúng trên nhánh;
     - `confirmed`: đã qua cổng `auditor` (`eslint --max-warnings 0`), `Reviewer`, `Hydrogen docs` và được `copilot-git` xác nhận `merged`/`deployed` trên `BRANCHES.md`.
   - `waiting`: nhánh đang chờ (`blocked` / `depends_on`) thì theo dõi trên `BRANCHES.md` và `resume` sau, **tuyệt đối không tạo nhánh/task trùng (`never create a duplicate`)**.
   - `/walk 3 real examples`: đi qua **3 ví dụ thực tế (bắt buộc gồm cả ca lỗi / biên thất bại)** trước khi đóng gói vào `.agents/tasks/<ID>.md`.
4. **`04 / improve.self` — Tự soi lỗ hổng từ dữ liệu thật:**
   - Tự đọc `.agents/reviews/`, `.agents/log/`, `agm inbox`; khi có lỗi, truy ngược theo mã định danh (`join_on`: mã việc `<ID>`, commit SHA, mã terminal `t...`) để tìm khoảng trống (`find the gap`). Nếu thiếu dữ liệu kiểm chứng → đề xuất viết thêm rule ESLint/script check nhỏ.
5. **`05 / routines` — Tự động hóa để người dùng không còn là điểm nghẽn:**
    - Thiết lập `trigger` rõ ràng (thả tệp `.agents/inbox/<ID>.md`, sự kiện `agm daemon`, hàng đợi `BRANCHES.md`). Chỉ tự động giao hoặc mở tiếp phiên khi nguồn và phần ngân sách đã được duyệt; nếu wrapper không kiểm được điều này thì việc dùng Go hoặc nguồn tính phí phải qua CEO thủ công.
6. **`06 / review` — Trả kết quả khởi tạo chuẩn:**
    - Đối chiếu lại `process vs goal`, chốt phân bổ kinh phí (nguồn, mức theo việc, dự phòng review/sửa, điểm dừng) và kết thúc bằng khối tóm tắt:
      `return { goal, process, rules, routine, budget, next_step }`
   - Sau đó hỏi đúng **1 câu xác nhận cuối** trước khi chuyển sang Bước 1–9 bên dưới.

---

### 5.1. Chín bước thực thi của BOT-CEO sau khi đã chốt `goal + process`

Mỗi BOT-CEO vận hành theo 9 bước gọn:

1. **Khởi động, trao đổi trực tiếp & quản lý vòng đời BOT-CEO qua `agm`:**
   - Mở thẳng phiên BOT-CEO trong HERDR / `herdr-core` với tên chuẩn theo lane (tối đa 32 ký tự `a-z 0-9 - _`), ví dụ `ceo-tap-hoa`, `ceo-platform`, để bạn chat/trao đổi nhiều lượt trực tiếp ngay trong phiên đó.
   - Bật **`agm manage ceo-tap-hoa`** (cài `agm hook install` một lần nếu dùng Claude Code): khi BOT-CEO làm dài và ngữ cảnh chạm `ctx_rotate` (mặc định 70%), `agm daemon` tự nhắc ghi bàn giao vào `.agents/handoff/` rồi mở phiên BOT-CEO kế nhiệm sạch ngữ cảnh — **không bao giờ kill phiên cũ**, vừa tránh phình ngữ cảnh vừa giữ nguyên mạch công việc của lane.
2. **Research & Bàn thiết kế (chỉ đọc, trong checkout chính):**
   - Dùng GitNexus (`query`, `context`, `impact`) để giảm tối đa số tệp phải đọc; kiểm `BRANCHES.md` xem các lane khác có mục `wip`/`ready` nào chạm cùng điểm nóng không.
   - Tra cứu web: `agm ask` qua `agy`; đọc mã/tóm tắt cần sớm: Flash Go trong mức cấp. Tổng hợp không gấp có thể giao NVIDIA chỉ đọc sau kiểm dữ liệu/quota/qualification; không chờ nó để sang các cổng chính. Bàn thiết kế sâu: phiên `agy` Opus High khi còn hạn mức.
3. **Giữ chỗ trên `BRANCHES.md`:** ghi mục `status: wip`, `lane`, `touches_hotspot`, `depends_on` (qua `agm branch set <lane>/<slug> status=wip ... --file <abs>/BRANCHES.md` hoặc tool MCP `agm_branch_update`).
4. **Tạo worktree & giao thợ trực tiếp qua `agm spawn` (ưu tiên model nhẹ trước):**
     - Tạo `.agents/tasks/<ID>.md` (mục tiêu, phạm vi, `tier:`, `skills:` tối đa 2, lệnh kiểm, nguồn/model, mức cấp và yêu cầu tương tác/nền). Fast/mid ưu tiên Flash Go đã qualification; việc vượt năng lực chuyển Pro phù hợp hoặc Codex ca khó trong mức cấp, không chỉ đổi template cùng model. Miễn phí/local đủ năng lực đã duyệt là dự phòng.
    - CEO kiểm [Go Console](https://opencode.ai/console/go) và ngân sách trước khi giao, đổi nguồn hoặc mở phiên lại. Nếu Go cạn/không rõ hạn mức, chọn nguồn đã duyệt đủ năng lực hoặc chuyển `blocked`; không chuyển tự động sang API ngoài gói.
   - Chạy `dispatch.sh <ID>` (gọi `agm spawn` hoặc `agm_spawn`): tự kiểm `max_workers` (chỉ tính `--role worker`) và ngân sách `task:<ID>`, tạo worktree riêng, gắn nhãn `agm.task`/`agm.role`. Khi có nhiều đầu việc độc lập (tệp/module/test tách biệt), đặt `wip` và **khởi động song song trong cùng một đợt** trong mức `max_workers` và ngân sách Go đã duyệt — không chờ xong từng việc một.
5. **Theo dõi & gỡ vướng:**
   - Thợ báo cáo hoặc hỏi trực tiếp về BOT-CEO của lane qua `agm send`; câu hỏi cần người dùng quyết đi thẳng vào `agm send user --type HỎI ...` (bạn trả lời tập trung trong `agm tui` hoặc `agm reply`).
    - Nếu thợ chạm `ctx_rotate`, ghi và commit `.agents/log/<ID>.md` trước khi bàn giao. Chỉ dùng tự xoay vòng Go khi đã kiểm cơ chế giữ đúng model và không vượt phần được cấp; nếu không, CEO duyệt khi mở phiên kế nhiệm.
6. **Cổng kiểm chất lượng của lane:**
   - **Audit & Cổng ESLint/CI (model nhẹ / miễn phí):** chạy `eslint --max-warnings 0` (hoặc `ruff`/`clippy -D warnings`), quét diff chặn `eslint-disable`/`@ts-ignore`/sửa cấu hình lint ([docs/ESLINT-CI-GUARDRAILS.md](docs/ESLINT-CI-GUARDRAILS.md)), chạy test/build + kiểm quy ước (`git diff` trong phạm vi, có `.agents/log/<ID>.md` & test mới). Vi phạm lint hoặc tự tắt rule → trả `CHƯA ĐẠT` ngay mà không tốn token gọi Reviewer.
     - **Reviewer (1 tầng cho nhánh thường):** ưu tiên Pro Go đã qualification trong phần chừa cho review; Pro đã viết code thì chọn model khác họ đủ năng lực đã duyệt. Phiên mới độc lập, không đọc suy luận của thợ. Dự phòng `agy` đã duyệt; ca khó/rủi ro giữ thang leo Opus/Codex/Claude. CHƯA ĐẠT thì chuyển nguyên văn lỗi về thợ; hết quota không bỏ review.
   - **Cập nhật docs & tổng hợp báo cáo (ưu tiên model nhẹ):** với báo cáo cuối `.agents/reports/<ID>.md` và 1–2 mục docs ngắn, dùng **`gemini-3.8-flash-medium` hoặc `gemini-4-hydrogen-low`**; chỉ dùng **`gemini-4-hydrogen-medium`** khi sửa tài liệu kiến trúc dài/nhiều tệp, rồi commit trên nhánh.
7. **Rebase & chốt `ready`:**
   - Rebase nhánh lên `main` mới nhất (nếu xung đột hoặc lệch migration head thì xử lý ngay trong worktree), chạy lại lệnh kiểm chứng, lấy `HEAD_SHA=$(git rev-parse --short=12 HEAD)`.
   - Cập nhật mục trên `BRANCHES.md` bằng `agm branch set ... status=ready head=$HEAD_SHA verify=... review=... docs=... registered=... --worktree <đường dẫn worktree>` (hoặc `agm_branch_update`): `status: ready`, `head: $HEAD_SHA`, `verify`, `review`, `docs`, `registered`.
8. **Bàn giao cho `copilot-git` & cập nhật GitNexus:**
   - Nhắn ngắn qua `agm send copilot-git --type GIAO --task <ID> "Nhánh <lane>/<slug> ready tại SHA $HEAD_SHA, xem BRANCHES.md"`.
   - Nếu `copilot-git` trả `needs-rebase` hoặc `failed`, BOT-CEO chuyển về `wip`, xử lý trên worktree và đăng ký `ready` lại với SHA mới.
    - Khi `deployed`/`merged`, làm mới chỉ mục tại checkout chính bằng `gitnexus analyze --index-only` (ưu tiên script/hook; dùng `gitnexus-sync` miễn phí/cục bộ nếu cần agent), rồi dọn worktree/terminal theo phạm vi hiện có.
9. **Chuyển bài học lớn cho Gemini Argon:**
     - Cuối đợt, BOT-CEO đối chiếu mức đã cấp với số đo và lần đổi nguồn, trả phần dự phòng chưa dùng về ngân sách lane/chung. Nếu lane gặp lỗi lặp lại ≥ 2 lần, ghi nguyên nhân + đường dẫn bằng chứng vào `.agents/decisions/` (hoặc báo `argon-adv`) để **Gemini Argon** tối ưu harnessing.
     - Có thể giao NVIDIA Nemotron tổng hợp log làm đầu vào cho Argon, không thay Argon quyết định/sửa harness. Brief nền có deadline (pilot đề xuất 15 phút), SHA/snapshot và phạm vi đọc. Kết quả muộn/lệch SHA phải đối chiếu lại; lỗi nghiêm trọng vẫn báo ngay. Hết hạn không mở task trùng khi task cũ chưa kết thúc.

---

## 6. Giới hạn & quy tắc cứng khi vận hành nhiều BOT-CEO

| Tham số | Khuyến nghị | Cách thực thi |
|---|---|---|
| Số BOT-CEO đồng thời | ≤ 4–5 lane | Mỗi lane mở một terminal `ceo-<lane>` có `agm manage` |
| Tổng thợ OpenCode đồng thời trên máy | Theo `[policy].max_workers` trong `~/.agmag/providers.toml` | `agm spawn` chặn cứng khi chạm trần |
| Trần token mỗi việc | `agm budget set task:<ID> --soft ... --hard ...` | `agm daemon` cảnh báo; `agm spawn` chặn khi chạm trần đã đo |
| Hạn mức Go và kinh phí mỗi lane | CEO phân bổ trong trần người dùng duyệt | Kiểm Console trước khi mở phiên; không dùng trần token `agm` thay hóa đơn/hạn mức Go |
| NVIDIA nền liên lane | Ban đầu tối đa 1 tác vụ trên toàn nhóm alias; chỉ đọc | Một CEO hiện có kiểm thủ công; `max_workers` không tự chặn mọi vai nền. `429` thì dừng giao thêm và kiểm `Retry-After`/quota, không đổi alias để né |
| Số migration đang `wip`/`ready` mỗi lane | Tối đa 1 | Kiểm tra khi viết mục `BRANCHES.md` |
| Số `copilot-git` | **Đúng 1** | Hàng đợi merge/deploy luôn tuần tự |
| Quyền dừng BOT-CEO (Claude/Codex) | **Chỉ người dùng** | `agm kill` từ chối mọi agent tự ý kill Claude/Codex |

### Điều BOT-CEO không bao giờ làm
- Không đọc sâu mã của lane khác nếu không liên quan điểm chạm (tránh phình ngữ cảnh).
- Không sửa `BRANCHES.md` bằng tay hoặc tự `mkdir` khóa; chỉ ghi qua `agm branch set` / `agm_branch_update`.
- Không đặt `ready` khi chưa có kết quả Audit + Reviewer (+ cập nhật docs của Hydrogen Medium nếu có thay đổi).
- Không tự merge, push `main` hoặc deploy (giao `copilot-git`).
- Không tự bật Extra Usage, tăng trần/nâng gói hoặc dùng nguồn phát sinh phí chưa duyệt. Không coi số liệu Go thiếu là còn hạn mức.
- Không tự nới lỏng quy tắc cứng của harness; đề xuất cải tiến harness chuyển qua **Gemini Argon** và cần người dùng duyệt đối với thay đổi cấp độ quy tắc cứng/quyền.

---

## 7. Mẫu prompt khởi động một BOT-CEO (theo khung Lauren Tan)

```text
role := Bạn là Claude BOT-CEO phụ trách lane <tên-lane> (terminal: ceo-<tên-lane>). Bạn làm chủ mục tiêu và điều phối kinh phí AI của lane trong trần người dùng đã duyệt.
Hãy đọc AGENTS.md, BOT-CEO.md và kiểm tra trạng thái wip/ready hiện có trong BRANCHES.md.

goal := <MỤC TIÊU CUỐI CÙNG BẠN MUỐN ĐẠT ĐƯỢC> cho lane <tên-lane>
input (brain dump) :=
- ...
- ...

Làm đúng theo thứ tự Goal First -> Process Second -> Then Routines (Mục 5.0 của BOT-CEO.md):
1. [goal.first & process.dump] Thu thập steps, watch_outs (điểm nóng), tools, check_work (eslint/test), info_from, feedback_from; xác định việc này phục vụ revenue hay cost.
2. [hold] Diễn đạt lại (/restate) goal + process, đi qua 3 ví dụ (gồm ca lỗi/biên), chốt nguồn và dự phòng, xuất { goal, process, rules, routine, budget, next_step } và hỏi tôi ĐÚNG 1 CÂU mỗi lượt nếu còn quyết định ẩn.
3. KHÔNG gọi agm spawn hay sửa mã cho tới khi tôi xác nhận kế hoạch.
4. Khi tôi chốt "chạy": giữ chỗ wip bằng `agm branch set`. Kiểm hạn mức: DeepSeek Flash Go cho fast/mid/explore, Pro Go cho review/strong phù hợp sau qualification; script/CI cho việc xác định. NVIDIA nền chỉ đọc, không chặn merge. Không tự bật Extra Usage hoặc dùng API ngoài gói; thiếu hạn mức thì nguồn đã duyệt đủ năng lực hoặc CHẶN. Done khi qua Audit -> Reviewer -> Docs (nếu cần) -> copilot-git.
```

---

## Nguồn tham khảo

- Khung xác định mục tiêu `Automate Anything` (`goal + process + routines`): Lauren Tan (`poteto`)
- Mô hình gốc đa lane + `BRANCHES.md` + khóa thư mục (bản gốc; `agm` đã thay bằng `agm branch set`): `/mnt/d/Project/MATHY-AI/HARNESSING.md`, `/mnt/d/Project/MATHY-AI/BRANCHES.md`, `/mnt/d/Project/MATHY-AI/docs/harness/CEO_BOT.md`, `/mnt/d/Project/MATHY-AI/docs/harness/CAI_TIEN_HARNESS.md`
- Bộ điều phối `agm` (`agmag` v0.4.0): `/mnt/d/Project/agmag/README_vi.md` (hoặc https://github.com/wosonday/agmag/)
- Tài liệu cùng bộ: [AGENTS-TUTORIAL.md](AGENTS-TUTORIAL.md), [HERDR-CORE-BOT.md](HERDR-CORE-BOT.md)
