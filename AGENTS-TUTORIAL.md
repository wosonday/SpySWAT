# Chỉ dẫn làm việc với đội agent (phiên bản 3.6: DeepSeek Go + NVIDIA nền + Claude + Codex + GitHub Copilot + Google Gemini / agy + HERDR + agm)

Chỉ dẫn dùng chung cho dự án code hoặc việc khác (tài liệu, báo cáo, phân tích).

> **Thứ tự ưu tiên tài liệu (từ cao xuống thấp):** `AGENTS.md` / `CLAUDE.md` của từng dự án **>** `AGENTS-TUTORIAL.md` (quy tắc cứng, quyền & cổng phát hành) **>** [BOT-CEO.md](BOT-CEO.md) (mở rộng khi tách nhiều lane) **>** [HERDR-CORE-BOT.md](HERDR-CORE-BOT.md) (hạ tầng `agm`/`hc`). Hướng dẫn chi tiết cho từng model nằm ở [docs/README.md](docs/README.md).

> **Cập nhật 3.6 (2026-11-20):** đã mở Go; ưu tiên **`opencode-go/deepseek-v4.1-flash`** cho `worker-fast/mid` và tìm mã/tóm tắt cần phản hồi sớm; **`opencode-go/deepseek-v4-pro`** cho Reviewer thường và `worker-strong` phù hợp, sau kiểm chứng năng lực theo vai và trong phần được cấp. Script/CI vẫn làm việc xác định, miễn phí/cục bộ là dự phòng đã duyệt. **NVIDIA chỉ làm việc nền, chỉ đọc, không chặn merge** theo [hướng dẫn riêng](docs/NVIDIA-BACKGROUND.md). Bậc năng lực không phải tốc độ. v3.6 thay thế mặc định chọn nguồn của v3.5/v3.4; nhật ký cũ không phải chỉ dẫn giao việc hiện hành.
>
> **Cập nhật 3.5 (2026-11-20, lịch sử):** Claude CEO điều phối kinh phí; Go cho việc vừa/review. Chính sách ngân sách vẫn giữ tại [§3.1.1](#311-điều-phối-kinh-phí-ai); routing hiện hành xem [hướng dẫn DeepSeek Go](docs/OPENCODE-WORKERS-REVIEWER.md).

> **Cập nhật 3.4 (2026-11-19):**
> - **Bảo toàn hạn mức Claude Code & Codex:** chỉ mở Claude Code cho **Kiến trúc sư / BOT-CEO** (và ca leo thang rủi ro cao). **Opus High qua `agy`** được giữ dưới dạng **phiên tương tác trong repo** (`--mode plan --sandbox`, giữ `conversation_id` để tận dụng `cache_read_tokens`, **không** dùng `agm ask` one-shot) để làm **Đồng Kiến trúc sư (bàn thiết kế/chia việc thay Claude)** và **Reviewer cấp cao phân xử ca khó** (nhánh thường bỏ bước Pre-review để không tốn 2 lần model lớn). Vì OpenCode chạy `openai/gpt-6.1-sol` **tiêu chung hạn mức ChatGPT (5h/7d) với Codex CLI**, tách **Reviewer mặc định** sang OpenRouter / Ollama Cloud hoặc `agy` (`gemini-4-argon-high` / `gemini-4-hydrogen-high`); giữ Codex (`gpt-6.1-sol`) cho **engineering khó** và **review chéo ca phức tạp**. Khi bật `BOT-CEO.md`, **bỏ tầng `codex-mgr` trung gian thường trực**; còn báo cáo `.agents/reports/<ID>.md` chuyển sang model rẻ / Hydrogen Medium.
> - **Mặc định miễn phí của v3.4 (đã thay thế):** từng ưu tiên OpenRouter `:free`/Ollama cho Audit, tìm mã và thợ nhanh. Không suy từ nhật ký này rằng DeepSeek hiện miễn phí; chỉ dùng ID và nguồn đã xác minh theo v3.6.
> - **Cập nhật tài liệu tự động theo cổng:** **Gemini 4 Hydrogen Medium** (`gemini-4-hydrogen-medium` qua `agy`) nhận lệnh cập nhật docs khi có thay đổi (và có thể tổng hợp luôn `.agents/reports/<ID>.md`) **sau khi Reviewer đã duyệt/chỉnh sửa và trước khi gọi GitHub Copilot**.
> - **Cố vấn kỹ thuật & tối ưu Harnessing:** **Gemini Argon** (`gemini-4-argon-*` qua `agy`) đóng vai trò cố vấn kỹ thuật giống Codex, với trách nhiệm đặc thù là cập nhật và tối ưu hóa hệ thống harnessing giữa các phiên để khắc phục những vấn đề lớn của phiên trước (bao gồm hiệu chỉnh phân bậc `tier:` cho model miễn phí).
> - **Bỏ phần ảnh 2D/3D và video** khỏi chỉ dẫn chung (nếu dự án nào cần, sẽ tối ưu riêng trong harness của dự án đó).
> - **Điều phối nền bằng `agm` (`agmag` v0.4.0):** thay cơ chế theo dõi/giao tiếp thủ công trong `herdr-core` bằng `agm` (`agm daemon`, `agm spawn`, `agm send`, `agm ask`, `agm inbox`, `agm tui`, `agm branch`, `agm mcp`, xoay vòng và ngân sách). Chi tiết xem [HERDR-CORE-BOT.md](HERDR-CORE-BOT.md) và [docs/AGM-0.4.0-GUIDE.md](docs/AGM-0.4.0-GUIDE.md).
> - **Mô hình đa mảng (BOT-CEO):** với dự án lớn cần tách nhiều mảng độc lập để tránh phình ngữ cảnh, xem [BOT-CEO.md](BOT-CEO.md).
> - **Hướng dẫn riêng từng model:** xem [docs/README.md](docs/README.md).

> **Cập nhật 3.3 (2026-11-18):** giao quản lý phiên bản Git cho **GitHub Copilot**: tích hợp nhánh, lịch sử, revert và dọn nhánh đã tích hợp. Với MATHY-AI, Copilot nhận vai bot GIT theo `docs/harness/GIT_BOT.md` (hướng dẫn chung xem [docs/COPILOT-GIT.md](docs/COPILOT-GIT.md)).

> **Cập nhật 3.2 (2026-11-18):** cách cài/nâng cấp OpenCode v2 (`@opencode/cli`, tự cập nhật, bẫy dịch vụ nền trên Windows) và nơi v2 lưu đăng nhập — mục 2.1. Với MATHY-AI, bản vận hành chính thức nằm ở `HARNESSING.md` §5.3, §5.7.

> **Cập nhật 3.1 (2026-11-17, bổ sung 2026-11-18):** thêm mục 4.2.1, gồm kết quả chạy `hc` (herdr-core 0.1.21) trên máy thật Windows 11.

## 0. Tóm tắt mô hình

- **Mỗi phiên OpenCode = một lập trình viên riêng**, làm trên một git worktree riêng, nên nhiều feature chạy song song mà không đè lên nhau.
- **Việc cơ khí** (viết code theo đặc tả, sửa lỗi nhỏ, chạy test, tìm trong repo, đổi tên) giao cho OpenCode. Model của từng phiên có thể đổi bất cứ lúc nào theo yêu cầu của Codex hoặc Opus.
- **Kiến trúc sư** (Claude Code: Opus 5.5 Extra hoặc Fable 5.2; khi tách nhiều mảng thì mỗi lane là một **BOT-CEO** theo `BOT-CEO.md`) quyết định hướng đi, rủi ro và phân bổ kinh phí AI trong trần người dùng đã duyệt. **Claude Code chỉ mở cho vai Kiến trúc sư / BOT-CEO** và ca leo thang rủi ro cao.
- **Đồng Kiến trúc sư & Reviewer cấp cao** (**Opus High qua `agy`**, chạy phiên tương tác trong repo `--mode plan --sandbox` / nối `--conversation <id>` để tận dụng `cache_read_tokens`) gánh thay trực tiếp tải của Claude Code khi bàn thiết kế/chia việc và phân xử review các nhánh phức tạp (không dùng làm bước Pre-review thừa cho nhánh thường).
- **Reviewer mặc định** ưu tiên **`opencode-go/deepseek-v4-pro`**, sau qualification, trong phiên mới độc lập. Nếu Pro đã viết code thì chọn model khác họ đã duyệt đủ năng lực, không tự review bằng cùng model; `agy` (`gemini-4-argon-high` / `gemini-4-hydrogen-high`) là dự phòng trong hạn mức. Chỉ gọi Codex review chéo logic khó; `agy` Opus High phân xử, Claude Opus High cho bảo mật/dữ liệu/migration/kiến trúc lớn hoặc `CHƯA ĐẠT` 2 lần. Không bỏ review khi thiếu quota.
- **NVIDIA nền** chuẩn bị tổng hợp, đề xuất tài liệu và phân tích log cho đợt sau. Chỉ đọc; không tự sửa code/docs chính thức, không là Reviewer hoặc cổng trước merge. Model/độ trễ/chất lượng chưa benchmark; xem [NVIDIA-BACKGROUND.md](docs/NVIDIA-BACKGROUND.md).
- **Cập nhật tài liệu (Docs)** (**Gemini 4 Hydrogen Medium** qua `agy`) nhận lệnh cập nhật docs khi có thay đổi (và tổng hợp `.agents/reports/<ID>.md` nếu có), thực hiện **sau khi nhánh đã qua Reviewer / chỉnh sửa xong và trước khi gọi GitHub Copilot**.
- **Codex (`openai/gpt-6.1-sol`)** là kỹ sư chuyên sâu cho **engineering khó** (sửa lỗi 2 lần chưa đạt, refactor đa tệp) và **quản lý các phiên OpenCode ở dự án 1 luồng** (khi bật `BOT-CEO.md`, BOT-CEO gọi thẳng thợ, không đặt thêm tầng `codex-mgr` trung gian). Lưu ý: OpenCode dùng `openai/gpt-6.1-sol` tiêu **chung** hạn mức ChatGPT với Codex CLI — luôn theo dõi `agm quota`.
- **Gemini Argon** (`gemini-4-argon-*` qua `agy`) đóng vai trò **cố vấn kỹ thuật** tương tự Codex, nhưng phụ trách phần đặc thù là **cập nhật và tối ưu hóa các harnessing** (`AGENTS.md`, `CLAUDE.md`, `.agents/`, template, skill, cổng kiểm) để các phiên sau cải thiện được những vấn đề lớn của phiên trước.
- **GitHub Copilot quản lý phiên bản Git:** nhận nhánh và SHA đã qua kiểm tra (và đã cập nhật docs nếu có) để tích hợp; xử lý lịch sử, revert/rollback và dọn nhánh trong phạm vi được cho phép.
- **Mọi agent ghi nhật ký và lưu tệp `.md` ngay trên nhánh đang làm**, commit cùng với code, và kiểm các thay đổi bằng git trước khi bàn giao (mục 3.3).
- Các phiên chạy trong **herdr / herdr-core (`hc`)**, được theo dõi, gửi tin có ghi sổ, giới hạn ngân sách và xoay vòng qua **`agm`** (bộ điều khiển `agmag`, mục 3.2 và 4.2); `herdr-mesh` chỉ dùng bổ sung nếu chạy trong HERDR TUI độc lập. Khi trao đổi với Kiến trúc sư/BOT-CEO, người dùng mở thẳng phiên trong HERDR và chat trực tiếp (kèm `agm manage`), còn `agm` lo đo token, hộp thư và `agm ask` một lượt.

### 0.1. Kiến trúc tổng thể

```
             HERDR / herdr-core (hc) + agm (daemon, TUI, sổ sách, policy)
                              |
              ORCHESTRATOR & CỐ VẤN
              (Kiến trúc sư / BOT-CEO · agy Opus High [đồng kiến trúc] · Codex [1 luồng] · Gemini Argon)
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
   Research / Audit     Developer Agent      Reviewer Agent
   - web: agy           - fast/mid: Go Flash - Mặc định: Go DeepSeek Pro
   - explore: Go Flash  - strong: Go Pro    - Dự phòng: model khác họ / agy
   - Audit: script/CI   - khó: Codex        - Ca khó: agy Opus High / Codex
                                             - Rủi ro cao: Claude Opus High
          |                   |                   |
          +-------------------+-------------------+
                              |
              GIT WORKSPACE (mỗi phiên một worktree + nhánh)
                              |
               TEST / VALIDATION (Audit + Pre-check: model miễn phí)
                              |
               REVIEWER (1 tầng cho nhánh thường; ca khó dùng agy Opus High)
                              |
               DOCS & REPORT UPDATE (Gemini 4 Hydrogen Medium, nếu có thay đổi)
                              |
               GIT INTEGRATION (GitHub Copilot, đúng SHA)
                              |
                GITNEXUS UPDATE (script --index-only; agent :free/local nếu cần)
                              |
               HARNESS RETRO & OPTIMIZATION (Gemini Argon cho phiên sau)
               ^ NVIDIA nền: tổng hợp/log/đề xuất, chỉ đọc, không chặn merge
                              |
               FINAL REPORT (Hydrogen Medium / model rẻ tổng hợp, mục 8)
```

Cách đọc sơ đồ:

1. **HERDR / herdr-core (`hc`)** là nơi chạy và quan sát mọi phiên; **`agm`** là kênh giao tiếp ghi sổ (`agm send`), hộp thư (`agm inbox`), theo dõi token/ngữ cảnh, áp ngân sách và xoay vòng phiên (mục 3.2, 4.2).
2. **Orchestrator & Cố vấn** gồm: Kiến trúc sư (hoặc từng BOT-CEO theo mảng trong `BOT-CEO.md`), **Opus High qua `agy`** (đồng Kiến trúc sư giữ phiên trong repo để gánh bớt việc bàn thiết kế/chia việc cho Claude), Codex (quản lý ở dự án 1 luồng; ở chế độ BOT-CEO thì lùi về vai engineering khó để không trùng vai điều phối), và **Gemini Argon** (cố vấn kỹ thuật + tổng kết vấn đề lớn để cập nhật, tối ưu harnessing cho phiên sau). Orchestrator không tự làm phần việc code chính của thợ.
3. **Ba nhánh thực thi chính:**
   - *Research / Audit Agent* = vai Tìm kiếm & Kiểm tra. Web dùng `agy`; tìm mã/tóm tắt cần tương tác ưu tiên DeepSeek Flash Go trong mức cấp. Audit chạy script/CI; chỉ gọi model miễn phí/cục bộ đã duyệt khi cần diễn giải. Tổng hợp không gấp có thể giao NVIDIA nền, không chờ để qua cổng.
   - *Developer Agent* = vai Thợ cơ khí. `worker-fast/mid` ưu tiên DeepSeek Flash Go; `worker-strong` có thể dùng Pro đã kiểm chứng, Codex cho engineering thực sự khó. Không đủ Go thì chọn nguồn miễn phí/cục bộ đủ năng lực đã duyệt hoặc `blocked`; giữ nguyên worktree khi đổi nguồn.
   - *Reviewer Agent:* Nhánh thường chỉ duyệt **1 tầng độc lập** bằng **OpenCode Go** (dự phòng `agy` đã duyệt); không dùng hạn mức ChatGPT/Codex cho bước này. Ca khó/bất đồng mới gọi **`agy` Opus High** hoặc **Codex** review chéo; Claude Code chỉ leo thang ca rủi ro cao theo mục 0.
4. **Git workspace & Docs Update:** mọi kết quả đi qua nhánh/worktree. Sau khi nhánh qua Reviewer (và đã chỉnh sửa xong nếu có lỗi), **Gemini 4 Hydrogen Medium** nhận lệnh cập nhật docs khi có thay đổi và commit trên nhánh đó trước khi chuyển SHA cho GitHub Copilot.
5. **Test / Validation** là cổng Audit ở mục 6; chưa đạt thì quay lại Developer Agent (lỗi chuyển nguyên văn).
6. **Harness Optimization & Final Report:** Gemini Argon rút kinh nghiệm để tối ưu harness; Docs/model nhẹ tổng hợp báo cáo và CEO đối chiếu kinh phí theo mục 8.

## 1. Vai trò và model

| Cấp | Vai | Model đề xuất | Công cụ | Quyền | Việc |
|---|---|---|---|---|---|
| 1 | Kiến trúc sư (hoặc BOT-CEO theo lane) | Opus 5.5 Extra hoặc Fable 5.2 | Claude Code (`/model`, kèm `agm manage`) | Chỉ đọc mã; ghi hồ sơ điều phối và `BRANCHES.md` có khóa nếu áp dụng | Phương án, rủi ro, tiêu chí đạt, **điều phối kinh phí AI**, chẩn đoán lỗi khó, đánh giá SẴN SÀNG trước phát hành. **Đây là vai chính duy nhất mở Claude Code thường xuyên** |
| 1–2 | Đồng Kiến trúc sư & Reviewer cấp cao | **Opus High qua `agy`** (**[KIỂM]** mã model chính xác bằng `agy models`) | Antigravity CLI `agy --mode plan --sandbox` (giữ phiên tương tác trong repo / `--conversation <id>`, **không** dùng `agm ask` one-shot) | Chỉ đọc | Bàn thiết kế, phản biện phương án, chia `.agents/tasks/<ID>.md` thay Claude Code khi cần tiết kiệm hạn mức Claude; duyệt / phân xử các nhánh khó hoặc khi Reviewer mặc định phân vân |
| 2 | Reviewer (mặc định) | **`opencode-go/deepseek-v4-pro`** sau qualification; khác họ nếu Pro đã viết code; dự phòng `agy` đã duyệt | OpenCode (`opencode run --agent reviewer` / `agm spawn --role review`) hoặc `agy` | Chỉ đọc mã + ghi `.agents/reviews/` | Phiên độc lập, 1 tầng cho nhánh thường; lỗi kèm bằng chứng; giữ thang leo ca khó/rủi ro cao |
| 2 | Kỹ sư chuyên sâu & Quản lý (Codex) | `openai/gpt-6.1-sol` (Codex CLI / OpenCode) | Codex CLI | Đọc; sửa code **khi nhận việc engineering khó**; quản lý thợ OpenCode ở dự án 1 luồng | Làm các task khó/refactor/fix sau 2 lần fail (khi `agm quota` cho phép); ở dự án 1 luồng (không bật `BOT-CEO.md`) chia đầu việc, giám sát thợ và bàn giao Copilot |
| 2 | Cố vấn kỹ thuật & Tối ưu Harness | **Gemini Argon** (`gemini-4-argon-medium` / `gemini-4-argon-high`) | Antigravity CLI `agy` (chỉ đọc qua `agm ask` để cố vấn/review; phiên `agy` trong worktree riêng khi sửa harness) | Đọc; chỉ ghi vào tệp harness/điều phối khi được giao | Cố vấn kỹ thuật độc lập giống Codex; phân tích các vấn đề lớn của phiên vừa chạy để **cập nhật và tối ưu hóa harnessing** (`.agents/`, `AGENTS.md`, `CLAUDE.md`, template, skill, cổng, ngưỡng `tier:`) cho các phiên sau |
| 2 | Quản lý phiên bản Git | Model chọn trong GitHub Copilot | GitHub Copilot CLI (`copilot`) | Tích hợp đúng SHA đã kiểm chứng; thao tác nhánh/lịch sử theo phạm vi cho phép | Merge, revert/rollback, dọn nhánh đã tích hợp; ghi SHA và kết quả kiểm; push/tag/phát hành cần quyền của người dùng |
| 3 | Cập nhật tài liệu (Docs) & Báo cáo | **Bậc nhẹ trước:** `gemini-3.8-flash-medium` / `gemini-4-hydrogen-low` (docs nhỏ & `.agents/reports/<ID>.md`); **bậc vừa:** `gemini-4-hydrogen-medium` (tài liệu kiến trúc dài/nhiều tệp) | Antigravity CLI `agy` (trong worktree nhánh cần cập nhật) | Chỉ sửa tài liệu / docs & `.agents/reports/` trong phạm vi được giao | Nhận lệnh cập nhật docs + báo cáo cuối **sau khi Reviewer đã chỉnh sửa/duyệt xong và trước khi gọi GitHub Copilot**; commit trên cùng nhánh |
| 3 | Thợ cơ khí | **Flash Go** cho `worker-fast/mid`; **Pro Go** cho `worker-strong` phù hợp; nguồn miễn phí/cục bộ đã duyệt làm dự phòng | OpenCode trong worktree riêng | Sửa đúng phạm vi; cấm sửa cấu hình lint hoặc thêm `eslint-disable`/`@ts-ignore` | Lint + typecheck + test đạt trước bàn giao; nâng bậc theo năng lực, không theo độ trễ |
| 4 | Tìm kiếm & Tóm tắt log | Web: Gemini Flash/Argon qua `agy`; trong repo cần phản hồi sớm: **Flash Go**; không gấp: NVIDIA nền đã qualification | `agy`, OpenCode | Chỉ đọc | Trả vị trí kèm bằng chứng, không gửi cả log dài vào CEO |
| 4 | Audit & Cổng ESLint/CI | **Script/CI trước**; miễn phí/cục bộ đã duyệt nếu thật sự cần LLM diễn giải | Script/CI, OpenCode khi cần | Chạy lệnh, ghi `.agents/log/`, không sửa mã nguồn | Chạy lint/test/build, chặn lách rule theo [ESLINT-CI-GUARDRAILS.md](docs/ESLINT-CI-GUARDRAILS.md); không gọi Go chỉ để chạy lệnh |
| 4 | Tổng hợp nền NVIDIA | Kimi / Mistral / Nemotron: ID và vai thử nghiệm tại [hướng dẫn NVIDIA](docs/NVIDIA-BACKGROUND.md) | OpenCode, phiên chỉ đọc đã khóa quyền | Không sửa tệp hoặc sinh agent | Trả đề xuất cho điều phối; không chặn merge, không thay Review/Audit/Docs/Argon |
| 4 | Cập nhật GitNexus (`gitnexus-sync`) | **Không cần LLM**, hoặc model miễn phí/cục bộ nếu cần xử lý báo cáo | Script/CI, hoặc `agm spawn gitnexus-sync --role index` | Chỉ chạy lệnh `gitnexus` (`status`, `analyze --index-only`, `clean`) & kiểm tra MCP server; không sửa code hay tệp harness | Làm mới chỉ mục sau merge, khi `staleness` báo `behind`/`diverged`, hoặc khi worktree đổi cấu trúc |

Ghi chú:

1. Tên model cụ thể của OpenCode do người dùng cấu hình trong `opencode.json` (định dạng `nhà-cung-cấp/model`). Chỉ dẫn này chỉ quy định **bậc** (nhanh / vừa / mạnh), không cố định tên.
2. Với cấu hình v2 mới, khai báo agent trong `.opencode/agents/<tên>.md` với `model` và `permissions` (`edit`, `shell`) riêng. Khi chạy phiên chính, kiểm model thực tế đã chọn; chọn agent không tự đổi model đang lưu trong phiên.
3. Phần **tạo ảnh 2D/3D và video** không còn nằm trong bộ vai trò dùng chung; nếu dự án nào cần, sẽ bổ sung và tối ưu riêng trong harness của dự án đó.
4. Tên “bậc Nhanh” là tên tương thích cũ của `tier: nhanh`, **không phải cam kết latency**. Brief ghi riêng cần phản hồi tương tác hay nền, hạn hoàn thành, nguồn/model và quyền dữ liệu. Đây là chỉ dẫn điều phối, không là khóa scheduler mới trong `agm`.

### 1.1. Skill theo vai

Skill nói **cách làm**; tệp tác vụ nói **làm gì**. Khi mâu thuẫn, quy tắc dự án và `tasks/<ID>.md` thắng.

**Hạn mức khi khởi tạo một phiên (bắt buộc):**

1. Mỗi phiên khi khởi tạo chỉ nạp **1 đến 3 skill**.
2. **Thợ cơ khí tối đa 2 skill.**
3. Cần skill khác thì **thay** skill cũ (hoặc mở phiên mới), không cộng dồn.
4. Skill do Codex (hoặc Kiến trúc sư) chọn theo loại việc và ghi vào trường `skills:` trong `.agents/tasks/<ID>.md`, ví dụ `skills: test-driven-development, verification-before-completion`. Phiên chỉ dùng đúng các skill đã ghi.
5. Không nạp skill kiểu "phải gọi skill trước mọi hành động" cho thợ, Audit, Tìm kiếm, Docs và bot; chúng kéo thêm skill thiết kế và hỏi đáp vào việc cơ khí, và có thể làm phiên chạy nền treo chờ người trả lời.

| Vai | Số skill khi khởi tạo | Gợi ý (chọn theo giai đoạn) |
|---|---|---|
| Kiến trúc sư | 1 đến 3 | `brainstorming` (giai đoạn hiểu yêu cầu), `system-design` hoặc `architecture` (giai đoạn thiết kế/ghi quyết định); đổi skill khi sang giai đoạn khác |
| Đồng trao đổi (`agy` Opus High) | 0 đến 1 | Không cần nạp nhiều; đọc thẳng phương án/diff + `.agents/tasks/<ID>.md` |
| Codex quản lý | 1 đến 3 | `writing-plans`, `dispatching-parallel-agents`, `using-git-worktrees`; `testing-strategy` hoặc `requesting-code-review` khi cần, thay cho skill không còn dùng |
| Gemini Argon (Cố vấn & Harness) | 1 đến 2 | Đọc `AGENTS.md`, `.agents/log/`, `.agents/reviews/`, `.agents/decisions/` để tổng kết lỗi hệ thống và cập nhật harness |
| GitHub Copilot quản lý Git | 0 đến 1 | `verification-before-completion` nếu hỗ trợ; ưu tiên playbook Git của dự án |
| Reviewer | 1 đến 2 | `code-review`, `verification-before-completion` |
| Cập nhật docs (`agy` Hydrogen Medium) | 0 đến 1 | Đọc diff nhánh + `tasks/<ID>.md` + docs hiện hữu |
| Thợ cơ khí | **1 đến 2** | Xem bảng loại việc bên dưới |
| Audit | 0 đến 1 | `verification-before-completion` |
| Tìm kiếm | 0 đến 1 | Skill "exploring" của GitNexus (nếu dùng) |
| Cập nhật GitNexus (`gitnexus-sync`) | 0 | Chỉ chạy `gitnexus` CLI & `agm send` |
| Bot | 0 | Chỉ cần `agm` và `hc` |

**Chọn skill cho thợ theo loại việc (tối đa 2):**

| Loại việc | Skill |
|---|---|
| Thêm tính năng, có đặc tả rõ | `test-driven-development` + `verification-before-completion` |
| Sửa lỗi | `systematic-debugging` + `verification-before-completion` |
| Sửa theo kết quả duyệt (CHƯA ĐẠT) | `receiving-code-review` + `verification-before-completion` |
| Việc cơ khí đơn giản (đổi tên, định dạng) | 1 skill hoặc không có |

**Cách gắn và kiểm soát:**

1. Giữ bộ skill chung trong repo (một nguồn); OpenCode đọc được `.opencode/skills`, `.claude/skills`, `.agents/skills`. **[KIỂM]** đường dẫn skill của Codex.
2. Giới hạn theo vai bằng danh sách cho phép trong chỉ dẫn mở đầu (phần thân template) và trường `skills:`; nếu công cụ có cấu hình quyền skill theo từng agent thì dùng thêm. **[KIỂM]** với OpenCode.
3. Script giao việc từ chối đầu việc có quá 2 skill cho thợ (xem `HERDR-CORE-BOT.md`, mục 1.5).
4. Kiểm chứng: chạy cùng một đầu việc mẫu có và không có skill; giữ skill nào làm giảm số lần CHƯA ĐẠT hoặc số lượt sửa lại. Ngưỡng 1 đến 3 và tối đa 2 là kinh nghiệm, cần hiệu chỉnh theo kết quả thật.

## 2. Bậc model cho thợ OpenCode và cách đổi (Đổi hàng rào ESLint/CI lấy Model nhẹ)

| Bậc | Dùng khi | Ví dụ |
|---|---|---|
| Nhanh (**mặc định ưu tiên**) | Mọi việc rõ đặc tả trong phạm vi **≤ 2–3 tệp** đã có hàng rào `eslint --max-warnings 0` (hoặc `ruff`/`clippy`) + test tự kiểm ([docs/ESLINT-CI-GUARDRAILS.md](docs/ESLINT-CI-GUARDRAILS.md)) | Tìm trong repo, chạy test/lint, đổi tên, định dạng, **CRUD, UI component, API handler, viết unit test/fixture, refactor cục bộ** |
| Vừa | Việc liên kết 3–5 tệp, logic nhiều nhánh phức tạp hoặc vừa fail 2 lần ở bậc Nhanh | Luồng nghiệp vụ đa module, tích hợp dịch vụ ngoài |
| Mạnh | Việc khó đa tệp, thuật toán/đồng thời phức tạp, hoặc phiên vừa thất bại ở bậc Vừa | Lỗi race condition, migration dữ liệu phức tạp, tối ưu hiệu năng |

Quy tắc đổi:

1. Codex hoặc Opus được **yêu cầu đổi model hoặc mở phiên mới** khi: thợ sửa 2 lần chưa đạt; việc rõ ràng khó hơn dự kiến; hoặc việc dễ hơn dự kiến (hạ bậc để tiết kiệm).
2. Khi đổi model, giữ nguyên worktree và nhánh; giao lại bằng bản tóm tắt (đã làm gì, còn gì, lỗi nguyên văn) ghi vào tệp tác vụ (mục 3.2) rồi báo qua `agm send` (hoặc `herdr-mesh` nếu ở TUI).
3. Chỉ Codex hoặc Opus được đổi model của thợ. Thợ không tự đổi.

### 2.1. Nguồn cung cấp model (DeepSeek Go, NVIDIA, Ollama, OpenRouter)

OpenCode là phần mềm chạy thợ; model đến từ các **nhà cung cấp (provider)** cấu hình trong `opencode.json`. Khóa API nhập bằng `/connect` hoặc `opencode auth login`, không nằm trong repo. Mã model có dạng `provider_id/model_id`.

**Cài và cập nhật OpenCode (đã kiểm 2026-11-18, Windows 11):**

1. Cài bản v2 bằng `npm install -g @opencode/cli`. Gói `opencode-ai` trên npm là dòng **v1 cũ**; trình cài bằng `curl` cũng có thể để lại bản v1 ở `~/.opencode/bin`. Kiểm bằng `opencode --version` (phải là 2.x) trong **mọi** shell (PowerShell, Git Bash).
2. Bật tự cập nhật: thêm `"update": "auto"` vào `~/.config/opencode/opencode.json` (giá trị khác: `"notify"`, `"disable"`).
3. Trên Windows, **thoát hẳn OpenCode trước khi nâng cấp**: dịch vụ nền `opencode serve --service` giữ tệp `.exe`, làm `opencode upgrade` / `npm i -g` treo và có thể xóa mất lệnh `opencode`. Nâng cấp cũng dừng mọi phiên thợ đang chạy.
4. v2 lưu thông tin đăng nhập trong SQLite `~/.local/share/opencode/opencode.db` (xem `opencode debug paths`), **không còn** `auth.json`. Script nào cần biết provider đã đăng nhập phải đọc `opencode auth list` (hoặc tệp khai báo riêng), không đọc `auth.json`.

**Các nguồn:**

| Nguồn | Cách nối | Ưu | Nhược / lưu ý |
|---|---|---|---|
| **OpenCode Go** | Đã mở; kiểm đúng môi trường worker bằng `/models` | Flash cho fast/mid/explore; Pro cho review/strong phù hợp sau qualification | Các model trả phí Go dùng chung hạn mức 5 giờ/tuần/tháng. Không đổi Flash sang Pro để né cạn quota; không tự bật Extra Usage |
| **NVIDIA NIM** | Ba alias `nvidia-kimi`, `nvidia-mistral`, `nvidia-nemotron` đã có trong catalog | Việc nền chỉ đọc, không gấp | Chưa benchmark; chưa xác minh phí/quota. Không suy ba alias có ba hạn mức; xem [NVIDIA-BACKGROUND.md](docs/NVIDIA-BACKGROUND.md) |
| **Ollama chạy cục bộ** | Chạy Ollama và tải model; v2 tự dò tại `127.0.0.1:11434`. Nếu cần URL riêng, dùng `providers.ollama.settings.baseURL` theo [hướng dẫn v2](https://opencode.ai/docs/providers/#ollama) | Không tốn phí token; mã không rời máy | Phụ thuộc phần cứng. Ollama khuyến nghị cửa sổ ngữ cảnh tối thiểu 64k cho OpenCode; nếu gọi công cụ lỗi, tăng `num_ctx` |
| **Ollama Cloud** | Lấy khóa API tại ollama.com (Settings, Keys), chạy `opencode auth login` rồi chọn Ollama Cloud; hoặc `ollama launch opencode`. Endpoint `https://ollama.com`, biến môi trường `OLLAMA_API_KEY`. Model cloud có hậu tố `:cloud` | Model lớn không cần GPU cục bộ; Ollama gợi ý `glm-4.7:cloud` cho OpenCode | Mã gửi lên dịch vụ ngoài; có giới hạn số model cloud chạy đồng thời theo gói (xem bên dưới) |
| **OpenRouter** | `/connect` → OpenRouter; lấy ID `openrouter/<slug>` từ danh mục đang có | Một khóa truy cập nhiều model | Mã gửi lên dịch vụ ngoài; không mặc định dùng model ngoài gói tính phí |

**Gói và giới hạn của Ollama Cloud (biến động, phải xem lại trên ollama.com/pricing):** các trang tôi đọc không thống nhất. Một số nêu số model cloud chạy đồng thời theo gói (Free 1, Pro 3, Max 10); một số nêu Ollama đã chuyển sang tính theo token từ 31/08/2026, gói Pro 20 USD kèm 60 USD sử dụng, Max 100 USD kèm 300 USD, và bậc 0 USD trả theo mức dùng. Vì thế `max_workers` trong `~/.agmag/providers.toml` **không được vượt giới hạn đồng thời của gói đang dùng**, nếu giới hạn đó còn áp dụng.

**Gán nguồn cho bậc model (mục 2):** đây là gợi ý, tên model phải kiểm theo danh mục hiện hành vì thay đổi liên tục.

| Bậc | Nguồn gợi ý |
|---|---|
| Nhanh | **`opencode-go/deepseek-v4.1-flash`** cho việc hẹp có test và tương tác; miễn phí/cục bộ đã duyệt là dự phòng |
| Vừa | **`opencode-go/deepseek-v4.1-flash`** trong phạm vi đã kiểm chứng; chuyển Pro khi cần thêm năng lực, không chỉ vì đổi tên tier |
| Mạnh | **`opencode-go/deepseek-v4-pro`** cho việc phù hợp đã qualification; Codex cho engineering khó; Opus cho phân xử/rủi ro cao theo vai |

**Chiến lược tận dụng tối đa model nhẹ / miễn phí (giảm tải hạn mức mà không gây vòng lặp `CHƯA ĐẠT`):**

1. **Khóa bằng hàng rào ESLint & CI bắt buộc ([docs/ESLINT-CI-GUARDRAILS.md](docs/ESLINT-CI-GUARDRAILS.md)):** ép mọi model tuân thủ bộ rule cứng (`max-lines ≤ 350`, `max-lines-per-function ≤ 70`, `complexity ≤ 10`, cấm `any`, cấm `@ts-ignore`/`eslint-disable`, cấm `catch {}` rỗng, cấm quên `await`). Lint bắt các lỗi tĩnh đã cấu hình, không thay test hoặc chứng minh đúng nghiệp vụ; chưa có số đo để cam kết tỷ lệ lỗi/thời gian. Nếu chèn chỉ thị tắt rule hoặc tự sửa cấu hình lint, Audit/CI phải chặn.
2. **Dùng đúng nguồn:** script/CI cho lint/test, diff và GitNexus. Khi cần LLM tương tác, tận dụng Flash Go trong mức cấp; Audit chỉ cần model miễn phí/cục bộ để diễn giải khi cần. NVIDIA nhận tổng hợp nền, không thay công việc script hoặc kéo dài cổng kiểm.
3. **Thang leo theo năng lực:** fast và mid có thể cùng dùng Flash nhưng khác phạm vi task. Sau 2 lần sửa không đạt hoặc việc vượt năng lực đã kiểm chứng, CEO cân nhắc Pro/engineering khó theo thang leo, không chỉ đổi template rồi kỳ vọng model mạnh hơn.
4. **Dự phòng chống nghẽn `429`:** với endpoint miễn phí, dùng nguồn miễn phí/cục bộ đã duyệt khác. Với Go, đối chiếu Console để phân biệt cạn hạn mức với giới hạn tốc độ hoặc lỗi tạm thời; không thử lặp hoặc đổi sang model Go khác để vượt hết hạn mức chung.
5. **Cắt token đầu vào bằng GitNexus & theo dõi qua `agm`:** dùng **GitNexus MCP** (`query`, `context`, `impact`) ở chế độ chỉ đọc để agent nhẹ không đọc tràn ngữ cảnh; định kỳ chạy `agm cost --by source` và `agm quota` để đo tỷ lệ token đã chuyển sang `opencode`/`agy`, rồi giao **Gemini Argon** chỉnh lại phân loại `tier:` nếu một nhóm việc dùng model nhẹ hay bị trả lại.

**Khai báo agent trong repo (mẫu v2, thay bằng ID đã kiểm):** Go không cần cấu hình provider thủ công; dùng `/connect`. Không đổi model mặc định toàn máy sang Go.

```markdown
---
description: Thợ bậc nhanh
mode: primary
model: opencode-go/deepseek-v4.1-flash
---
Đọc AGENTS.md và chỉ làm đầu việc đã giao trong worktree.
```

Lưu mẫu ở `.opencode/agents/worker-fast.md`; `worker-mid` ưu tiên cùng Flash, `reviewer` ưu tiên Pro đã duyệt. Agent gọi trực tiếp trong phiên riêng cần `mode: primary` hoặc `all`; khi chạy `opencode run`, truyền `--model` đã chọn để không kế thừa model khác. Mẫu này không cấp quyền chi phí và chưa là cấu hình đang chạy.

Với Ollama Cloud, đừng viết tay cấu hình; chạy `opencode auth login` hoặc `ollama launch opencode`, rồi lấy mã chính xác bằng `opencode models` (**[KIỂM]** mã provider thực tế).

**Quy tắc sử dụng:**

1. **Đổi nguồn do Codex hoặc Opus quyết định**, không do thợ (mục 2, quy tắc đổi). Khi nguồn bị giới hạn tốc độ hoặc lỗi, Codex đổi sang nguồn khác cùng bậc, giữ nguyên worktree, và ghi vào nhật ký.
2. **Dữ liệu nhạy cảm:** đầu việc chạm bảo mật hoặc dữ liệu (mục 5, quy tắc 2) chỉ dùng model cục bộ, hoặc phải được người dùng đồng ý trước khi gửi mã lên nguồn cloud.
3. **Khóa API:** chỉ lưu trong kho đăng nhập của OpenCode (`opencode auth login`) hoặc biến môi trường (`OLLAMA_API_KEY`, `OPENROUTER_API_KEY`) của dịch vụ chạy nền; không đưa vào repo, tệp tác vụ hay nhật ký.
4. **Chi phí:** Claude CEO phân bổ trong trần người dùng đã duyệt ([§3.1.1](#311-điều-phối-kinh-phí-ai)). `agm` chặn theo `max_workers` và trần token `task:<ID>` đã cấu hình, không thay được kiểm tra hạn mức Go hay trần tiền.
5. **Chọn model theo năng lực gọi công cụ:** thợ phải gọi công cụ ổn định (sửa tệp, chạy lệnh). Trước khi dùng model mới cho thợ, chạy thử một đầu việc mẫu: sửa một tệp trong worktree, chạy test, ghi nhật ký, commit. Model không qua thử nghiệm thì không được giao việc thật.
6. Tệp tác vụ có thể ghi trường `tier: nhanh | vừa | mạnh`; `dispatch.sh` chọn template tương ứng (`worker-fast`, `worker-mid`, `worker-strong`) khi gọi `agm spawn`.
7. **Catalog đã kiểm:** hai ID DeepSeek Go ở trên và ba ID NVIDIA có trong danh mục hiện tại; chưa có benchmark API trong đợt sửa tài liệu này. DeepSeek Go không là nguồn miễn phí và không đồng nhất với `opencode/deepseek-*` Personal/API. Kiểm lại danh mục khi giao việc.

### 2.1.1. NVIDIA nền — phương án A

- Giao việc tổng hợp cho đợt sau, soát tính nhất quán tài liệu, phân tích lỗi lặp trong log; không giao code hoặc duyệt nhánh.
- Chỉ đọc, trả đề xuất cho điều phối; không sửa docs chính thức hoặc hồ sơ của phiên khác. Vai Docs/Argon hiện có vẫn quyết định và ghi.
- Ban đầu CEO cấp **tối đa 1 việc NVIDIA cùng lúc trên cả ba alias**, deadline pilot đề xuất **15 phút**, quản lý thủ công; chưa có scheduler/cooldown tự động được kiểm chứng.
- Kiểm quyền cloud, phí/quota và qualification trước khi dùng. `429`/hết quota: dừng giao thêm trong phạm vi ảnh hưởng, theo `Retry-After`/reset; không đổi alias để né.
- Brief có task ID, SHA hoặc snapshot và thời điểm lấy; kết quả muộn/lệch SHA phải đối chiếu lại, không tự áp vào nhánh đã đổi. Không chờ báo cáo nền để merge; bằng chứng rủi ro nghiêm trọng vẫn phải báo.
- Quy trình chi tiết và bài qualification ở [NVIDIA-BACKGROUND.md](docs/NVIDIA-BACKGROUND.md).

### 2.2. Antigravity CLI `agy`: tìm kiếm, đồng trao đổi, docs, cố vấn & tối ưu harness

Người dùng dùng Antigravity CLI (`agy`) cho bốn vai trò riêng biệt (không còn dùng phần tạo ảnh 2D/3D và video dùng chung; dự án nào cần media sẽ tự tối ưu harness riêng):

| Vai trò | Model qua `agy` (kiểm danh sách bằng `agy models`) | Chế độ chạy | Ghi chú |
|---|---|---|---|
| **Tìm kiếm / research** | `gemini-3.8-flash-{low,medium,high}` (nhanh), `gemini-4-argon-{low,medium,high}` (sâu) | Chỉ đọc: `agm ask` (cho câu hỏi web độc lập 1 lượt) hoặc `agy --mode plan --sandbox` | Tìm mã tương tác trong repo dùng Flash Go trong mức cấp; tổng hợp nền có thể giao NVIDIA |
| **Đồng Kiến trúc sư & Reviewer cấp cao** | **Opus High qua `agy`** (**[KIỂM]** tên slug cụ thể trong `agy models`) | Phiên tương tác `agy --mode plan --sandbox` mở tại repo (hoặc nối `--conversation <id>`); **không** dùng `agm ask` one-shot | Tận dụng `cache_read_tokens` và tự đọc tệp trong repo để bàn thiết kế/chia việc thay Claude Code, hoặc phân xử review ca khó (bỏ Pre-review trên nhánh thường) |
| **Cập nhật tài liệu (Docs) & Báo cáo** | **`gemini-4-hydrogen-medium`** | Phiên `agy` trong worktree nhánh đang làm | Nhận lệnh cập nhật docs + tổng hợp `.agents/reports/<ID>.md` **sau khi Reviewer đã chỉnh sửa/duyệt xong và trước khi gọi GitHub Copilot**; commit trên cùng nhánh |
| **Cố vấn kỹ thuật & Tối ưu Harnessing** | **`gemini-4-argon-medium`** / **`gemini-4-argon-high`** | Chỉ đọc qua `agm ask` (hoặc script kiểu `argon_review.py` của `agmag`) để cố vấn/review; phiên `agy` trong worktree riêng khi sửa tệp harness | Đóng vai cố vấn kỹ thuật giống Codex, nhưng đặc thù phụ trách **cập nhật và tối ưu hóa harnessing** (`.agents/`, `AGENTS.md`, `CLAUDE.md`, template, skill, cổng) dựa trên các vấn đề lớn của phiên trước |

**Mẫu lệnh một lần (chỉ đọc, tự ghi token vào `agm`):**

```bash
# Cách ưu tiên: qua agm ask (tự chạy agy --mode plan --sandbox trong thư mục tạm ngoài repo và ghi token vào agm.db)
agm ask --model gemini-4-argon-high --timeout 300 "<câu hỏi hoặc đoạn diff/mã cần cố vấn>"

# Hoặc gọi agy trực tiếp ngoài repo (khi cần xuất JSON thô)
cd <thư-mục-tạm-ngoài-repo>
agy --model gemini-4-argon-medium --mode plan --sandbox --print-timeout 600s --output-format json \
  -p "<câu hỏi>. Mỗi kết luận kèm URL nguồn. Không sửa tệp." > research.json
```

**Quy tắc riêng cho các vai chạy qua `agy`:**

1. **Research là gợi ý, không phải sự thật.** Lần thử 2026-11-18, Gemini báo sai phiên bản một gói npm dù kèm đúng URL. Codex/Kiến trúc sư đối chiếu mọi con số, phiên bản, giá với nguồn gốc (lệnh `npm view`, trang chính thức) trước khi đưa vào tệp tác vụ.
2. `agy` có quyền riêng, **không** đọc quyền của agent OpenCode. Các vai chỉ đọc (Tìm kiếm, Đồng trao đổi, Cố vấn chỉ đọc) luôn chạy `--mode plan --sandbox` ở thư mục tạm ngoài repo (hoặc qua `agm ask`); không bao giờ `--dangerously-skip-permissions`.
3. **Vai sửa tệp qua `agy` (Hydrogen Medium sửa docs, Argon sửa harness):** chỉ mở phiên tương tác trong worktree đúng phạm vi và **chỉ giao đúng phạm vi được sửa** (docs với Hydrogen Medium; tệp harness/điều phối với Argon), không sửa code nghiệp vụ của thợ.
4. **Đo token trong `agm`:** `agm` tự quét token của phiên `agy` tương tác từ `transcript.jsonl` và ghi nhận `agm ask` riêng (khử trùng lặp); riêng phiên IDE không ghi `transcript.jsonl` chỉ đo được qua `agm ask`.
5. Dữ liệu gửi đi theo đúng quy tắc mục 2.1 quy tắc 2: không bí mật, không dữ liệu khách.

## 3. Điều phối và giao tiếp

### 3.1. Trách nhiệm

- **Người dùng:** quyết định về nghiệp vụ, quyền, dữ liệu, chi phí; phê duyệt phát hành; chỉ người dùng được dừng/ngắt phiên Codex hoặc Claude Code. Khi trao đổi nhiều lượt với Kiến trúc sư / BOT-CEO, người dùng mở thẳng phiên trong HERDR và chat trực tiếp (kèm `agm manage`), còn theo dõi/trả lời hộp thư và hỏi 1 lượt thì dùng `agm tui` / `agm ask`.
- **Kiến trúc sư (hoặc từng BOT-CEO theo lane trong `BOT-CEO.md`):** làm chủ mục tiêu cuối (`you own the goal, not the steps`), hiểu yêu cầu theo khung **Lauren Tan (`Goal first · Process second · Then routines`)** — hỏi từng câu một cho rõ quyết định ẩn, gom quy trình, đi qua 3 ví dụ thực tế (gồm cả ca lỗi), diễn đạt lại và **tạm dừng (`hold`) chờ người dùng xác nhận** rồi mới giao việc ([BOT-CEO.md §5.0](BOT-CEO.md)). Với mô hình đa mảng, **1 lane = BOT-CEO kiêm luôn Kiến trúc sư của lane đó**; chỉ mở Kiến trúc sư tổng khi thiết kế xương sống liên mảng.
- **Đồng Kiến trúc sư & Reviewer cấp cao (`agy` Opus High):** giữ phiên tương tác trong repo để bàn thiết kế/chia việc thay Claude Code khi cần tiết kiệm hạn mức Claude, và duyệt/phân xử các nhánh khó.
- **Reviewer (mặc định qua OpenCode Go, dự phòng `agy` đã duyệt):** duyệt độc lập theo bằng chứng diff/test (1 tầng cho nhánh thường); ca khó dùng `agy` Opus High / Codex, chỉ leo thang về Claude Code Opus High với ca rủi ro cao (bảo mật/dữ liệu/migration/2 lần `CHƯA ĐẠT`).
- **Codex:** chia phương án thành đầu việc, giao việc một lần cho đủ (mục tiêu, phạm vi được sửa, ràng buộc, tiêu chí đạt, mẫu báo cáo), theo dõi tiến độ, gỡ vướng cho thợ.
- **Gemini Argon:** cố vấn kỹ thuật song song với Codex, đồng thời phụ trách tổng kết vấn đề lớn sau mỗi phiên để cập nhật, tối ưu hóa harnessing cho các phiên kế tiếp.
- **Gemini 4 Hydrogen Medium:** nhận lệnh cập nhật docs khi có thay đổi sau bước Reviewer (trước khi gọi Copilot) và commit docs trên nhánh.
- **GitHub Copilot:** quản lý phiên bản Git; nhận nhánh + SHA + kết quả Audit/Review (+ commit docs nếu có) từ Codex, tích hợp tuần tự và kiểm lại sau merge. Không tự sửa lỗi nghiệp vụ; trả về quản lý khi xung đột.
- **Mỗi tệp/phần chỉ một phiên sửa tại một thời điểm.** Codex chịu trách nhiệm phân chia để các worktree không chồng phạm vi.
- Công cụ không tạo được phiên riêng thì một AI tự đóng lần lượt từng vai, đúng thứ tự.

#### 3.1.1. Điều phối kinh phí AI

1. **Người dùng đặt trần và duyệt ngoại lệ. Claude CEO chịu trách nhiệm phân bổ.** CEO xếp ưu tiên và cấp mức cho từng việc/lane, giữ phần dự phòng cho review và sửa lại, được giảm bậc, xếp lại hàng đợi hoặc đổi giữa các nguồn đã duyệt. Không tự bật **Extra Usage**, tăng trần, nâng gói, nạp tiền, hoặc dùng nguồn phát sinh phí ngoài gói khi chưa được người dùng duyệt. Dự án một luồng: Codex quản lý có thể giao việc trong phần CEO đã phân bổ, không tự tăng trần.
2. **Không đếm trùng hạn mức giữa các lane.** Nếu nhiều lane dùng chung một hạn mức Go, người dùng chỉ định **một CEO hiện có** làm đầu mối phân bổ chung; không mở bot mới. Các CEO lane báo phần đã dùng, phần đã cấp cho phiên đang chạy và dự phòng; đầu mối đối chiếu các khoản này với hạn mức còn lại trước khi cấp thêm.
3. **Kiểm trước mỗi đợt giao việc, lượt review hoặc lần nâng bậc.** Tra [OpenCode Go Console](https://opencode.ai/console/go) cho cả ba cửa sổ **5 giờ / tuần / tháng** và trạng thái Extra Usage; dùng cửa sổ có ít dư địa nhất để quyết định. Giữ Extra Usage tắt mặc định; nếu đang bật mà chưa có phê duyệt thì không giao Go. Các model trả phí `opencode-go/*` rút từ cùng hạn mức, tách với ChatGPT/Codex, Claude Code và `agy`. Dùng `agm quota` cho nguồn có số liệu đã xác minh; dùng `agm cost --by source` và `agm budget` để theo dõi token, **không** quy đổi token `opencode` thành % Go hoặc hóa đơn. Nếu không truy cập được Console, nhờ người dùng cung cấp số liệu gần nhất, không coi số chưa có là 0%.
4. **Tại ngưỡng cảnh báo do người dùng duyệt** (gợi ý bắt đầu ở 70% đã dùng của bất kỳ cửa sổ Go nào), giữ phần còn lại cho việc ưu tiên và review/sửa đang cam kết. Khi trần đã chạm, số liệu chưa xác minh, hoặc không đủ phần dự phòng: không mở thêm phiên Go; chuyển việc sang nguồn miễn phí/cục bộ hoặc nguồn trong gói khác đã duyệt **và đủ năng lực**, nếu không thì `blocked` chờ hạn mức đặt lại hoặc người dùng quyết. Không hạ yêu cầu review để tiết kiệm chi phí. Khi cần tăng chi, gửi một tin `agm send user --type HỎI --task <ID> "..."` nêu lý do, chi phí tăng dự kiến và phương án không tăng chi.
5. **Ghi quyết định và đối chiếu sau đợt chạy.** Trong brief hoặc nhật ký, ghi mã việc/lane, vai, `provider/model`, mức được phân bổ (kèm đơn vị), số hạn mức và thời điểm kiểm, phương án dự phòng, lý do đổi nguồn hoặc phê duyệt ngoại lệ nếu có. Báo cáo cuối tách số token đo được theo việc khỏi mức dùng Go tổng của tài khoản; ghi rõ số nào chỉ ước tính hoặc chưa xác minh. Không đưa khóa API, dữ liệu thanh toán hay ảnh Console vào repo.

### 3.2. Giao tiếp bằng `agm` (trên `herdr-core`) và `herdr-mesh`

**Kênh mặc định trong `herdr-core` là `agm send` / `agm inbox`** (từ dự án `agmag`, mục 5–6 của `README_vi.md`). `agm` bọc `hc send` nhưng **ghi lịch sử tin nhắn vào `~/.agmag/agm.db`**, tự nhận diện người gửi qua biến `HC_TERMINAL_ID`, và định tuyến tin gửi `user` vào **hộp thư người dùng** (`agm inbox` / `agm tui`).

1. **Cho agent dùng `agm` (`v0.4.0`):** thêm đoạn sau vào `AGENTS.md` và `CLAUDE.md` của dự án:
   - **Agent quản lý / duyệt (BOT-CEO, `copilot-git`, `reviewer`):** có thể gọi trực tiếp **7 tool MCP của `agm mcp`** (`agm_send`, `agm_inbox`, `agm_ps`, `agm_quota`, `agm_spawn`, `agm_branch_get`, `agm_branch_update`) thay cho gõ CLI. **Không gắn `agm` MCP cho profile thợ (`worker-*`)** vì MCP có `agm_spawn`.
   - **Ghi `BRANCHES.md` an toàn:** luôn dùng `agm branch get/set` hoặc `agm_branch_update` (agm tự giữ khóa nguyên tử, không `mkdir` khóa bằng tay; thợ bị từ chối ghi `BRANCHES.md`).
   - Gửi tin cho agent khác (CLI hoặc `agm_send`): `agm send <tên-terminal> --type ASSIGN|REPORT|ERROR|QUESTION|BLOCKED|PASS|FAIL --task <ID> "<nội dung ngắn>"` (chấp nhận cả mã tiếng Anh và mã tiếng Việt tương đương `GIAO|BÁO CÁO|LỖI|HỎI|CHẶN|ĐẠT|CHƯA ĐẠT`; CSDL vẫn lưu mã tiếng Việt)
   - Cần người dùng quyết định: `agm send user --type HỎI --task <ID> "<câu hỏi>"` (hoặc `QUESTION`, vào hộp thư người dùng)
   - Xem hộp thư (quản lý / người dùng): `agm inbox --json` hoặc `agm_inbox`
   - Không dùng `agm kill` với phiên Codex/Claude — chỉ người dùng được làm việc đó.
2. **Tên agent / terminal:** chỉ gồm chữ thường, số, `-`, `_`, bắt đầu bằng chữ cái, tối đa 32 ký tự. Quy ước: `arch`, `sparring` (`agy` Opus High), `review`, `codex-mgr`, `argon-adv` (Gemini Argon), `docs-hyd` (Hydrogen Medium), `copilot-git` (quản lý Git), `gitnexus-sync` (cập nhật chỉ mục GitNexus), `w-<feature>-<số>` (thợ), `agm-daemon`. Cả `hc run --name` và `agm spawn` đều áp đúng giới hạn này, nên **mã việc `<ID>` phải viết thường**.
3. **Trước khi gửi / đọc kết quả:** `agm send` gọi `hc send --if idle` nên an toàn khi đích đang làm việc; mỗi lần chỉ gửi một tin ngắn một đến ba dòng, một việc. Khi cần đọc đầu ra màn hình, dùng `hc read <t> --lines N` (chỉ lấy phần mới, không đọc cả pane để tiết kiệm ngữ cảnh).
4. **Thông tin bền vững ghi vào tệp, không chỉ nằm trong tin nhắn.** Tin nhắn chỉ là tín hiệu và con trỏ. Đặc tả, quyết định, kết quả kiểm, tóm tắt bàn giao ghi vào `.agents/tasks/<ID>.md` (hoặc `log/`, `decisions/`, `reviews/`) trong worktree/nhánh và tin nhắn chỉ trỏ tới tệp đó.
5. **Nếu chạy trong HERDR TUI độc lập (không qua `agm`):** có thể dùng `herdr-mesh` (MCP bọc CLI `herdr`: `herdr install`, `claude mcp add -s user herdr-mesh herdr-mesh`, gửi bằng `herdr_relay`; bản `herdr-mesh-safe` có lease cho controller/reviewer/writer). Tuy nhiên **trên `herdr-core` đã có `agm` + `hc`**, không bắt buộc phải cài `herdr-mesh`.

Mẫu tin nhắn bắt buộc (ngắn, một tin một việc — khớp định dạng `agm send`):

```
agm send <đích> --type GIAO|BÁO CÁO|LỖI|HỎI|CHẶN|ĐẠT|CHƯA ĐẠT --task <ID> "<tóm tắt 1-2 câu; xem .agents/tasks/<ID>.md>"
```

Nội dung chuẩn khi hiển thị:

```
[LOẠI] [ID <ID>] từ <người-gửi>: <tóm tắt ngắn> (kèm kết quả kiểm số đếm nếu là BÁO CÁO)
```

Lỗi do Audit/Reviewer (hoặc `agy` Opus High khi phản biện trước) tìm ra được chuyển **nguyên văn** (qua tệp tác vụ/review) cho đúng thợ đã làm, thông qua Codex.

### 3.3. Sổ ghi chép trên nhánh và kiểm thay đổi kiểu git

Nguyên tắc: **git là nguồn sự thật về "đã đổi gì"; tệp `.md` ghi "vì sao" và "đã kiểm gì"**. Cả hai nằm trên cùng nhánh, đi cùng nhau.

**Cấu trúc thư mục (mỗi tệp theo mã việc `<ID>` nên không xung đột khi merge):**

```
.agents/
  tasks/<ID>.md         # đặc tả: mục tiêu, phạm vi sửa, ràng buộc, tiêu chí đạt   (Codex viết)
  log/<ID>.md           # nhật ký làm việc, chỉ thêm, không sửa cũ                 (thợ / Audit / Hydrogen docs viết)
  reviews/<ID>-<n>.md   # kết quả duyệt lần n: ĐẠT/CHƯA ĐẠT, lỗi, vị trí, cách sửa   (Reviewer / sparring viết)
  decisions/<ID>.md     # quyết định thiết kế, rủi ro, tối ưu harnessing           (Kiến trúc sư / Codex / Argon viết)
  reports/<ID>.md       # báo cáo cuối của nhánh (mục 8)                           (Codex viết)
```

*(Ghi chú: `.agents/handoff/` được `agm` tự thêm vào `git info/exclude` khi xoay vòng phiên Claude/Codex, không commit vào nhánh.)*

**Quy tắc ghi:**

1. **Mỗi tệp đúng người ghi** theo vai trò ở trên, đúng nguyên tắc "một phần, một người sửa". Thợ không sửa `tasks/`; muốn đổi đặc tả thì ghi đề xuất vào `log/` và báo Codex.
2. **Nhật ký chỉ thêm.** Sai thì thêm mục đính chính bên dưới, không xóa hay viết lại mục cũ.
3. **Commit sớm và nhỏ.** Mỗi bước có ý nghĩa (xong một phần, trước khi thử hướng rủi ro, trước khi bàn giao, sau khi Hydrogen Medium cập nhật docs) là một commit, **gồm cả code/docs và mục nhật ký tương ứng**. Thông điệp commit bắt đầu bằng `<ID>:`.
4. **Cấp quản lý & cố vấn cũng ghi:** Kiến trúc sư ghi `decisions/`, Codex ghi `tasks/`, `reports/` và các lần đổi model/phiên vào nhật ký điều phối, **Gemini Argon ghi đánh giá & thay đổi tối ưu harnessing** vào `decisions/` (hoặc nhánh tối ưu harness riêng), Reviewer ghi `reviews/`. Tất cả commit trên nhánh mà họ đang đứng.
5. Không ghi bí mật (khóa, mật khẩu, dữ liệu cá nhân) vào các tệp này.

**Mẫu một mục nhật ký:**

```
## 2026-11-19 21:05 · w-login-1 · bước 2/4
- Đã làm: ...
- Tệp đổi: src/a.ts, src/b.ts
- Kiểm: `npm test` → 42 đạt / 0 lỗi
- Quyết định: ... (lý do)
- Vướng/Hỏi: ...
- Commit trước đó: <mã ngắn>
```

**Kiểm thay đổi kiểu git (bắt buộc tại mỗi điểm bàn giao):**

1. Người bàn giao chạy `git status` (không còn tệp chưa commit, kể cả `.md`), `git diff --stat <nhánh-gốc>...HEAD` và `git log --oneline <nhánh-gốc>..HEAD`.
2. Đối chiếu danh sách "Tệp đổi" trong nhật ký với diff thực. Tệp đổi nằm ngoài phạm vi trong `tasks/<ID>.md`, hoặc đổi mà nhật ký không nhắc tới, là lỗi **Lớn** (CHƯA ĐẠT).
3. **Audit** kiểm thêm: nhật ký có mục cho mỗi commit, `.md` đã commit, lệnh kiểm ghi trong nhật ký chạy lại ra cùng kết quả.
4. **Reviewer** đọc `git diff <nhánh-gốc>...HEAD` kèm `tasks/` và `log/`; không đọc lập luận ngoài các tệp này (giữ tính độc lập).
5. **Cập nhật docs (nếu có thay đổi):** sau khi nhánh đã qua Reviewer / đã chỉnh sửa xong, **Gemini 4 Hydrogen Medium** cập nhật tài liệu liên quan trên đúng worktree nhánh đó, ghi một mục vào `log/<ID>.md` và commit để tạo SHA cuối.
6. **Codex** kiểm lại các bước trên, bàn giao nhánh + **SHA cuối** + kết quả Audit/Review (+ xác nhận cập nhật docs) cho **GitHub Copilot**. Copilot xác minh đúng SHA, tích hợp rồi chạy lại cổng kiểm tra. Khi có lỗi, chuyển nguyên văn qua `reviews/` hoặc nhật ký, rồi quay lại thợ.
7. Muốn xem lịch sử một việc, dùng `git log -- .agents/log/<ID>.md` hoặc `git log --oneline <nhánh>`. Muốn hoàn tác trên nhánh chung, giao **GitHub Copilot** thực hiện `git revert` và ghi mục đính chính; thợ chỉ commit trên nhánh riêng.

Khi tích hợp vào nhánh chung, giữ thư mục `.agents/` trong repo theo mặc định; Codex có thể quyết định loại khỏi bản phát hành nếu không muốn đưa ra ngoài.

### 3.3.1. Bàn giao quản lý Git cho GitHub Copilot

- Worker vẫn tạo commit nhỏ trên nhánh/worktree riêng; Hydrogen Medium commit phần cập nhật docs sau bước Reviewer. Codex quản lý việc và chuẩn bị gói bàn giao; Copilot phụ trách tích hợp và quản lý lịch sử trên nhánh chung.
- Gói bàn giao gồm: tên nhánh, SHA đầy đủ (sau commit docs nếu có), phạm vi diff, lệnh kiểm + kết quả thật, báo cáo Review/Audit, phụ thuộc và quyền push/phát hành đã có. Với MATHY-AI, CEO đăng ký vào `BRANCHES.md`; Copilot đọc hàng đợi theo `docs/harness/GIT_BOT.md` (hướng dẫn chung xem [docs/COPILOT-GIT.md](docs/COPILOT-GIT.md)).
- Mở `copilot` tại checkout tích hợp, yêu cầu đọc quy tắc dự án và playbook Git. Chỉ một phiên `copilot-git` xử lý hàng đợi, merge đúng SHA rồi kiểm lại. Xung đột nghiệp vụ hoặc test lỗi thì trả về quản lý, không tự sửa code để vượt cổng.
- Push, tag, phát hành và thao tác hủy lịch sử chỉ thực hiện khi người dùng đã cho phép. Dọn worktree/nhánh phải kiểm tra đã tích hợp, sạch và không còn phiên đang ghi.
- **Đã chạy thử Git** bằng Copilot CLI 1.0.113 trên fixture độc lập: 3/3 ca đạt, gồm dừng khi checkout bẩn, từ chối SHA sai và merge đúng SHA (xem báo cáo `docs/harness/COPILOT_GIT_SMOKE.md` trong repo `MATHY-AI`). Chưa nghiệm thu tích hợp toàn ứng dụng/deploy.
- **Chưa xác minh** Copilot CLI chạy trong HERDR/herdr-mesh trên máy này. Có thể mở terminal riêng và bàn giao bằng tệp; không mặc định dùng chung cấu hình MCP hoặc quyền của OpenCode.

### 3.4. Vòng đời của thợ: ngắn hạn theo đầu việc, ngữ cảnh nằm trong tệp

Vì trạng thái đã nằm trong `.agents/` và git, thợ là **thay thế được**; mặc định sống ngắn.

| Vai | Vòng đời |
|---|---|
| Tìm kiếm, Audit, Cập nhật GitNexus (`gitnexus-sync`), Cập nhật docs (`agy` Hydrogen Medium) | Sinh rồi diệt (hoặc chạy qua `agm ask` một lần cho tra cứu web) theo từng yêu cầu, không giữ trạng thái dài |
| Thợ cơ khí | Sống trong phạm vi một đầu việc; chỉ giữ qua nhiều đầu việc khi cùng feature và cùng vùng mã |
| Reviewer | Phiên mới cho mỗi lần duyệt (giữ độc lập); khi duyệt lại, đưa kết quả duyệt trước bằng tệp |
| Daemon (`agm daemon`) | Sống lâu nhưng không dùng LLM; chỉ lắng nghe `hc events`, đo token, kiểm ngân sách và xoay vòng |
| Kiến trúc sư / BOT-CEO, Đồng Kiến trúc sư (`agy` Opus High), Codex, Gemini Argon (cố vấn & harness) | Sống theo feature/đợt làm việc (với `agy` Opus High giữ `conversation_id` để ăn prompt cache), định kỳ nén hoặc xoay vòng ngữ cảnh, quyết định ghi vào tệp |
| GitHub Copilot quản lý Git | Một phiên riêng cho hàng đợi tích hợp; bàn giao bằng nhánh, SHA và log |

**Xoay vòng & thay phiên (do `agm daemon` theo dõi tự động hoặc gọi `agm rotate <t>`):**

- **Thợ OpenCode (`--role worker`):** khi đạt `ctx_warn` (mặc định 50%), `agm` cảnh báo hộp thư; khi đạt `ctx_rotate` (mặc định 70%) và rảnh, `agm` yêu cầu ghi bàn giao vào `.agents/log/<ID>.md` + commit, kiểm tra worktree sạch và có commit mới chạm tệp log đó, rồi dừng phiên cũ và mở phiên mới cùng template/cwd. Cũng thay phiên khi thợ sửa 2 lần chưa đạt (kèm nâng bậc model).
- **Phiên Claude Code & Codex đã bật `agm manage <t>`** *(lưu ý: `agm manage` chỉ hỗ trợ `claude-code` và `codex`, không áp dụng cho `agy` hay `copilot`)*: khi đạt `ctx_rotate`, `agm` yêu cầu ghi bàn giao vào `.agents/handoff/<id>-<ts>.md` (kết thúc bằng `<!-- agm:handoff-done -->`) rồi mở phiên mới đọc tệp đó; **`agm` không bao giờ tự kill phiên Claude/Codex cũ** (người dùng tự kiểm tra và dọn bằng `agm cleanup`).
- **Diệt/ngắt thủ công:** chỉ người dùng được dừng/ngắt Codex hoặc Claude Code qua `agm kill`/`agm interrupt` (phải xác nhận `y`).

### 3.5. Quy tắc sinh agent phụ

1. **Chỉ Kiến trúc sư và Codex được sinh agent** (qua `agm spawn`). Thợ, Reviewer, Audit, Hydrogen Medium và script nền không tự sinh. Độ sâu tối đa một cấp.
2. **Hai loại:** *subagent / hỏi một lần* (`agm ask` hoặc subagent chỉ đọc trong phiên) và *phiên riêng trong `herdr-core`* (`agm spawn`, có worktree riêng cho việc sửa mã hoặc cập nhật docs/harness).
3. **Giới hạn trao đổi:** thợ chỉ nhắn cho `ceo-<lane>` (hoặc `codex-mgr` ở dự án một luồng) qua `agm send`, không nhắn nhau. Mỗi agent phụ nhận một đầu việc, bộ công cụ tối thiểu và mẫu báo cáo định sẵn.
4. **Hạn mức:** trước khi `agm spawn`, `agm` kiểm `max_workers` cho vai `worker` và trần token `task:<ID>` đã cấu hình. Claude CEO kiểm riêng nguồn, hạn mức gói và quyền phát sinh chi phí ([§3.1.1](#311-điều-phối-kinh-phí-ai)); wrapper và phiên kế nhiệm không được dùng để né bước này.

### 3.6. Lớp ngữ cảnh mã nguồn: GitNexus (đã chọn)

GitNexus **không phải công cụ quản lý tác vụ**. Nó lập chỉ mục mã nguồn thành đồ thị phụ thuộc, chuỗi gọi hàm và luồng thực thi rồi đưa cho agent qua MCP. Việc quản lý tác vụ vẫn do `.agents/` và git đảm nhiệm.

**Giấy phép:** GitNexus dùng PolyForm Noncommercial. Dự án hiện tại không thương mại nên được dùng. Nếu sau này dự án chuyển sang thương mại, phải xem lại giấy phép hoặc chuyển sang phương án MIT như codebase-memory-mcp.

**1. Agent đọc được**

| Agent | Mức hỗ trợ |
|---|---|
| Claude Code | MCP, skill, hook |
| Codex | MCP, skill, hook (cài hook bằng `gitnexus setup -c codex`) |
| OpenCode | Dùng MCP và skill; không giả định dự án đã cài hook GitNexus |

**2. Cài đặt (làm một lần, trên nhánh riêng, do Codex thực hiện)**

1. Cài toàn cục để MCP khởi động nhanh và tránh quá thời gian chờ khi dùng `npx` lần đầu: `npm install -g gitnexus`.
2. Từ gốc repo: `gitnexus analyze --index-only` rồi `gitnexus setup` (tự dò Claude Code, Codex, OpenCode và ghi cấu hình MCP).
3. Với OpenCode, nếu cần cấu hình tay, khai báo trong `~/.config/opencode/config.json` mục `mcp`, máy chủ `gitnexus` kiểu `local`, lệnh `["gitnexus", "mcp"]`, hoặc nối qua một máy chủ HTTP dùng chung chỉ đọc (`GITNEXUS_MCP_READ_ONLY=1 gitnexus mcp --http --port 3111`).
4. **Lưu ý:** chạy `gitnexus analyze` **không** có `--index-only` sẽ tự cài skill, đăng ký hook của Claude Code và ghi đè `AGENTS.md`, `CLAUDE.md`. Vì vậy agent cập nhật chỉ mục **luôn dùng `gitnexus analyze --index-only`** (lần `setup` đầu tiên chạy trên nhánh riêng, xem `git diff`, giữ nguyên quy tắc dự án rồi mới commit).
5. Khi chạy một máy chủ MCP dùng chung cho nhiều client (`gitnexus mcp --http`), luôn bật `GITNEXUS_MCP_READ_ONLY=1` để công cụ `rename` không sửa nhầm lên checkout chính.

**3. Phân công dùng**

| Vai | Công cụ GitNexus nên dùng |
|---|---|
| Kiến trúc sư / BOT-CEO | `impact`, `context`, `generate_map` để đánh giá phương án và rủi ro |
| Reviewer (OpenCode) | Chủ động gọi `detect_changes`, `impact` qua MCP để kiểm phạm vi ảnh hưởng của diff |
| Thợ cơ khí | `impact` trước khi sửa; `rename` trong worktree khi đổi tên; `trace` khi tìm lỗi |
| Tìm kiếm | `query`, `context` |
| Cập nhật GitNexus (`gitnexus-sync`) | Chạy `gitnexus status`, `gitnexus analyze --index-only`, `gitnexus clean` (không gọi LLM cho phần lập chỉ mục) |
| Audit | Không cần |

**4. Giữ chỉ mục luôn mới qua agent `gitnexus-sync`**

1. Ưu tiên script/hook của dự án chạy **`gitnexus analyze --index-only`** tại checkout chính ngay sau khi Copilot tích hợp, hoặc khi `staleness.status` là `behind`/`diverged`. Nếu cần agent `gitnexus-sync` để kiểm và báo cáo, chọn model miễn phí/cục bộ, không dùng hạn mức Go.
2. Mỗi lần chỉ chạy **một** tiến trình `analyze` (dùng khóa `flock` hoặc thư mục khóa `.agents/locks/gitnexus`) để tránh xung đột kho chỉ mục hoặc ngốn RAM trên repo lớn.
3. Với worktree: mặc định `GITNEXUS_SHARED_STORE` để worktree dùng chung kho chỉ mục với checkout chính; nếu dự án cấu hình `GITNEXUS_SYNC=worktree` (chỉ mục riêng theo worktree), `gitnexus-sync` chạy `gitnexus analyze --index-only` khi tách worktree / đổi cấu trúc và `gitnexus clean` khi dọn worktree.
4. Nếu có máy chủ `gitnexus mcp --http` chạy nền, `gitnexus-sync` kiểm tra server còn phản hồi (và chạy `opencode reload` / kiểm `opencode mcp list` nếu cần), rồi báo kết quả (`BÁO CÁO` hoặc `LỖI`) qua `agm send`.

**5. Kiểm tra sau khi cài (làm trước khi giao việc thật):** thử ba việc trên chính repo: tìm nơi gọi một hàm, đánh giá ảnh hưởng của một thay đổi, đổi tên một ký hiệu; thực hiện từ cả Claude Code, Codex và OpenCode. Ghi kết quả vào `.agents/decisions/`.

**Phương án dự phòng:** nếu GitNexus không đạt (lệch chỉ mục giữa worktree, tốn bộ nhớ) thì thử codebase-memory-mcp (MIT) hoặc Serena (công cụ ngữ nghĩa dựa trên LSP).

## 4. HERDR, `hc` và `agm`: người điều khiển + nền tự động

### 4.1. HERDR (APP / TUI) và `agm tui`

- Dùng HERDR để mở các phiên Claude Code, Codex, OpenCode, `agy`, `copilot` cạnh nhau, xem trạng thái và can thiệp.
- Điều khiển từ xa: máy chủ chạy HERDR / `herdr-core`; từ điện thoại dùng **Moshi** (iOS/Android) kết nối vào máy chủ rồi gắn lại (attach) phiên (`hc attach <t>`).
- Mở **`agm tui`** trong một pane của herdr để quan sát tổng thể: hạn mức gói 5h/7d (% còn lại), trạng thái từng terminal + % ngữ cảnh, ngân sách đầu việc và **hộp thư người dùng** (câu hỏi từ agent, lỗi, cảnh báo xoay vòng).
  - Bảng TERMINALS: `name` (chấm `●` tô màu theo trạng thái như `hc`), `agent`, `model`, `effort`, `where` (vị trí herdr `workspace / tab`), `task`, `tokens`, `ctx`, `last msg` (`→ REPORT` = terminal đã gửi, `← ASSIGN` = vừa nhận), `status`.
  - Chọn tối đa 3 bảng bằng `view` (`quota`, `usage`, `terminals`, `budgets`, `inbox`; mặc định `quota terminals inbox`); **RECENT MESSAGES luôn hiện** ngay trên thanh lệnh. Khung in đầy đủ, lướt chuột để xem phần trên; chỉ vẽ lại khi dữ liệu đổi.
  - Lệnh gõ đầy đủ (vẫn nhận chữ cái đầu): `reply`, `done`, `send`, `cleanup`, `interrupt`, `kill`, `policy`, `view`, `quit`. Loại tin trong `send` dùng tên tiếng Anh `ASSIGN|REPORT|ERROR|QUESTION|BLOCKED|PASS|FAIL` (mã tiếng Việt cũ vẫn nhận; CSDL và `agm send --type` giữ mã tiếng Việt).
- Phiên của Kiến trúc sư, Reviewer, Codex, Argon nên dễ quan sát ở đây để người dùng đọc và phản hồi được.

### 4.2. Tự động hóa nền với `herdr-core` (`hc`) và `agm`

- **`agm daemon`** chạy nền trong `herdr-core` (`hc run --bg --no-parent --name agm-daemon agm daemon`) để lắng nghe `hc events --json`, quét token/hạn mức, kiểm ngân sách, mở hộp thư khi agent bị `blocked` và tự động xoay vòng phiên khi đầy ngữ cảnh.
- **Lớp wrapper công việc (worktree + inbox):** khi có đầu việc mới trong `.agents/inbox/<ID>.md`, script `dispatch.sh` (xem [HERDR-CORE-BOT.md](HERDR-CORE-BOT.md)) thực hiện:
  1. Tạo git worktree + nhánh mới: `git worktree add .wt/<ID> -b feat/<ID>` (hoặc đường dẫn quy ước của dự án như `../MATHY-AI.wt/<slug>`).
  2. Khởi động song song nhiều phiên thợ độc lập bằng **`agm spawn <template> --task <ID> --role worker --cwd <worktree> -- "..."`** (`--bg` không chặn, tự gắn `--outlive-parent`, kiểm `max_workers` chỉ đếm vai `worker` và ngân sách cứng, đặt tên `w-<ID>-<số>`).
  3. Khi thợ xong hoặc bị chặn, báo cho quản lý bằng **`agm send`** (hoặc `agm send user --type HỎI ...` nếu cần người dùng quyết); **không tự merge**.
- Giới hạn an toàn bắt buộc: `max_workers` và ngưỡng ngữ cảnh trong `~/.agmag/providers.toml`, trần token qua `agm budget set`, quyền `edit`/`shell` của OpenCode đặt rõ, nút dừng khẩn **`agm policy off`**, và **chỉ người dùng mới được `agm kill` phiên Codex/Claude**. Cổng kinh phí của CEO phải đứng trước wrapper/phiên tự động dùng Go hoặc nguồn tính phí.
- GitHub Copilot phụ trách dọn worktree/nhánh đã tích hợp và sạch; `agm cleanup` chỉ dọn các terminal cũ đã bàn giao trong `agm`/`hc` khi người dùng xác nhận.

### 4.2.1. `hc` trên máy thật (đã kiểm 2026-11-17, bổ sung 2026-11-18, hc 0.1.21, Windows 11)

CLI của herdr-core là `hc`. Thử nhanh bằng ba lệnh:

```powershell
hc run --bg --name demo ping -n 600 127.0.0.1   # chạy nền, trả JSON có "address":"t10", "state":"live"
hc ls                                           # liệt kê terminal đang sống
hc read demo --lines 10                         # đọc 10 dòng cuối, không cần attach
```

Những gì đã thấy trên máy thật (và xác minh bổ sung trong `.agents/decisions/p0-research.md` của `agmag` ngày 2026-11-18):

| Điểm | Kết quả thật | Hệ quả |
|---|---|---|
| Core | Đã chạy sẵn; `hc server start\|stop\|status\|restart` tồn tại. `hc server status` trả JSON có `live`, `finished`, `uptime_ms`, `version` | Dịch vụ khởi động cùng máy có thể dùng `hc server start`; còn phải thử sau khi khởi động lại máy |
| Đầu ra | Mặc định là JSON khi đầu ra đi qua đường ống; `run` và `read` in văn bản | `agm` đọc JSON trực tiếp từ `hc <lệnh> --json` |
| Dạng `hc ls` | Một **đối tượng** `{"hidden_finished": n, "terminals": [...]}`, **không phải mảng** | `agm` xử lý trực tiếp `.terminals`; script shell dùng `jq '.terminals \| length'` |
| Quan hệ cha–con | `hc run` gọi từ trong một terminal sẽ tự gán `parent` là terminal đó; `die_with_parent: true` theo mặc định | `agm spawn` luôn truyền `--outlive-parent` để thợ sống sót |
| Biến môi trường terminal | `hc` tự đặt `HC_TERMINAL_ID`, `HC_TERMINAL_SOCKET`, `HC_SCOPE` trong mỗi terminal | `agm send` tự nhận diện người gửi qua `HC_TERMINAL_ID`, và `agm` kiểm tra người gọi fail-closed |
| Báo trạng thái (OSC 7501) | Đã thấy các app tự báo 7501: `claude-code`, `codex`, `antigravity` (và `opencode` qua `hc ls`). Khi bị chặn có `state:"blocked"`, `kind:"question"\|"permission"`, `msg` | `agm daemon` bắt trực tiếp `status` `blocked` để đẩy nguyên văn câu hỏi vào hộp thư `agm inbox` |
| Tên terminal | `--name` chỉ nhận 1–32 ký tự `a-z 0-9 - _`, không chữ hoa | Mã việc phải viết thường (`test-1`, không phải `TEST-1`); cả `agm spawn` và `dispatch.sh` kiểm trước khi chạy |
| Vị trí & HERDR app | `labels` có `where` (vd `"MATHY-AI / Codex"`) và `herdr.space`/`herdr.tab` | **Terminal mở trong HERDR app hiện cả trong `hc` / `herdr-core`** |
| Sự kiện | `hc events --json`: dòng đầu là ảnh chụp `{"channel", "seq", "terminals"}`; các dòng sau dạng JSON-RPC (`created`, `finished`, `status`, `turn`, `title`, `labels`, `size`, `foreground`, `doc`) + `heartbeat` mỗi 15s | `agm daemon` tiêu thụ toàn bộ luồng sự kiện này |
| Template | `hc templates` ban đầu trả `{"templates": []}` | Phải tự tạo `worker-fast`, `worker-mid`, `worker-strong`, `auditor`, `researcher`, `docs-hydrogen`, `sparring-opus`, `argon-advisor` theo `HERDR-CORE-BOT.md` §1.4 |
| Dọn dẹp | `hc kill <t>`, `hc rm <t>`, `hc ls --all`, `hc run --rm` | Dùng `--rm` cho lệnh ngắn; không dùng cho thợ vì cần giữ để đọc log/ghép phiên |
| Báo khi con kết thúc | Khi terminal con thoát, `hc` tự gõ ghi chú `<hc>t10 demo exited...</hc>` vào agent cha (tắt bằng `--no-notify` hoặc `notes = false` trong `config.toml`) | Hữu ích khi cần biết nhanh con đã thoát; tắt nếu thấy rối prompt của agent cha |

Các lệnh khác của `hc`: `hc wait <t>` (dùng thay `sleep`), `hc interrupt <t>`, `hc keys <t> enter|esc|up|ctrl+c`, `hc put <t> <file>`, `hc exec`, `hc file read|write|edit`, `hc keep <t>`, `hc label <t> k=v`.

### 4.3. Phạm vi giao tiếp giữa HERDR app, TUI và `herdr-core`

- **Cập nhật đã xác minh (2026-11-18):** khi bắt sự kiện `hc events --json` trên Windows 11, các terminal mở trong **HERDR app** đều có mặt trong `hc` (với nhãn `herdr.space` / `herdr.tab` và `where`), nên **`agm` thấy, đo và giao tiếp (`agm send`) được với chúng**.
- Nếu người dùng chạy **HERDR TUI** ở phiên bản hoặc máy khác mà `hc ls` không thấy terminal của nhau, vẫn dùng phương án dự phòng: bàn giao qua tệp (`.agents/inbox/`, `.agents/tasks/`, `.agents/log/`) và git, hoặc chạy cả đội trong cùng một `herdr-core`.

## 5. Quy tắc giao việc

1. Tìm web → `agy`; tìm mã/tóm tắt cần sớm → Flash Go; tổng hợp không gấp → NVIDIA nền đã qualification. Audit → script/CI; miễn phí/cục bộ nếu cần diễn giải. Code hẹp/vừa → `worker-fast/mid` ưu tiên Flash Go có hạn mức và test.
2. **Điều phối theo ngân sách trước khi mở phiên:** Flash Go cho fast/mid/explore, Pro Go cho review/strong phù hợp theo [§3.1.1](#311-điều-phối-kinh-phí-ai). OpenCode dùng `openai/gpt-6.1-sol` với đăng nhập ChatGPT tiêu chung hạn mức với Codex CLI; giữ Codex cho ca khó, chỉ đổi nguồn trong mức được cấp.
3. **Claude Code chỉ mở cho Kiến trúc sư / BOT-CEO** và khi leo thang ca rủi ro cao: đổi cấu trúc lớn; việc chạm bảo mật/dữ liệu/migration DB; lỗi sửa 2 lần chưa xong (kể cả sau khi đã nâng bậc model); trước phát hành lớn.
4. Dùng **Opus High qua `agy`** (phiên tương tác trong repo / `--conversation <id>`, **không** gọi `agm ask` one-shot) để làm **Đồng Kiến trúc sư** (bàn thiết kế, chia `.agents/tasks/<ID>.md` khi muốn tiết kiệm hạn mức Claude Code) hoặc làm **Reviewer cấp cao** phân xử ca khó (bỏ bước Pre-review trên các nhánh thường).
5. Gọi **Codex (`gpt-6.1-sol`)** cho: **engineering khó / refactor đa tệp / fix lỗi sau 2 lần fail**, review chéo ca logic phức tạp, và làm **quản lý điều phối ở dự án 1 luồng** (khi đã bật `BOT-CEO.md`, BOT-CEO gọi thẳng thợ qua `agm spawn`, bỏ tầng `codex-mgr` trung gian thường trực).
6. Gọi **Gemini Argon (`agy`)** khi: cần cố vấn kỹ thuật độc lập như Codex, và **luôn giao Argon rà soát các vấn đề lớn sau phiên/giai đoạn để cập nhật và tối ưu hóa harnessing** (bao gồm tinh chỉnh bảng phân loại `tier:` cho model miễn phí) cho các phiên sau.
7. Gọi **Gemini 4 Hydrogen Medium (`agy`)** khi có thay đổi cần cập nhật docs (và tổng hợp báo cáo cuối `.agents/reports/<ID>.md`), thực hiện **sau khi Reviewer đã duyệt/chỉnh sửa xong và trước khi gọi GitHub Copilot**.
8. Gọi **GitHub Copilot** khi: quản lý nhánh/lịch sử, tích hợp đúng SHA, revert/rollback và dọn nhánh đã tích hợp.
9. Gọi **Reviewer mặc định (OpenCode Go; dự phòng `agy` Argon/Hydrogen High đã duyệt)** sau khi Audit & sàng lọc quy ước đạt, duyệt 1 tầng cho từng nhánh thường; ca khó dùng **`agy` Opus High** (hoặc Codex), và chỉ kéo **Claude Code Opus 5.5 High** vào duyệt lại với ca bảo mật/dữ liệu hoặc bị `CHƯA ĐẠT` 2 lần liên tiếp.
10. Sau chẩn đoán của Kiến trúc sư / BOT-CEO vẫn chưa xong thì dừng và hỏi người dùng (`agm send user --type HỎI ...`).

## 6. Cổng phát hành (làm đúng thứ tự)

**Lưu bản / commit trên nhánh worktree** → **Audit & sàng lọc quy ước đạt hết (script/CI, model miễn phí nếu cần)** → **Reviewer mặc định đạt / hoàn tất chỉnh sửa (Go hoặc nguồn dự phòng đã duyệt; leo thang theo mục 5)** → **Cập nhật docs & tổng hợp báo cáo nếu cần (Gemini 4 Hydrogen Medium nhận lệnh, sửa & commit trên nhánh; chạy lại kiểm nhanh nếu chạm phạm vi kiểm)** → **GitHub Copilot tích hợp đúng SHA cuối vào nhánh chung, chạy lại Audit** → **Cập nhật GitNexus (`analyze --index-only`)** → **Xem thử (nếu có giao diện)** → **Kiến trúc sư / BOT-CEO SẴN SÀNG** → **Phát hành (người dùng phê duyệt)** → **Xác minh môi trường thật** → *(Sau phiên/đợt: Gemini Argon tổng kết vấn đề lớn & tối ưu harnessing cho phiên sau)*

- Có lỗi ở bước nào thì sửa, lưu bản mới, chạy lại từ Audit.
- Kiểm không chạy được thì ghi rõ lý do, không báo là đạt.
- Trước mỗi cổng, kiểm thay đổi kiểu git theo mục 3.3 (không còn tệp chưa commit, nhật ký khớp diff, không sửa ngoài phạm vi).
- Bot/script nền và thợ không được phát hành; chỉ GitHub Copilot tích hợp, chỉ người dùng phê duyệt phát hành. Với MATHY-AI, Copilot triển khai theo phạm vi được cho phép và các cổng trong `GIT_BOT.md`.

## 7. Việc không phải code

Giữ nguyên đội hình và cổng. Kiến trúc sư lập dàn ý; (có thể phản biện trước qua `agy` Opus High); Codex hoặc BOT-CEO chia phần; mỗi thợ soạn một phần riêng (một worktree/tệp riêng); Tìm kiếm lấy nguồn, số liệu; Audit kiểm số liệu, mẫu, chính tả; Reviewer duyệt nội dung; Hydrogen Medium cập nhật tài liệu phụ trợ/chỉ mục liên quan trước khi Copilot chốt bản. "Commit" là lưu bản có số phiên bản; "phát hành" là gửi bản cuối. Mẫu người dùng đưa luôn giữ nguyên bố cục.

## 8. Báo cáo cuối

Do **Gemini 4 Hydrogen Medium** (lúc cập nhật docs cuối nhánh) hoặc **model rẻ (`:free` / `gemini-3.8-flash`)** tổng hợp từ `.agents/log/`, `reviews/` và `git diff --stat` rồi lưu vào `.agents/reports/<ID>.md`. Nêu thay đổi, phiên/model, số đếm kiểm chứng, kết luận review, docs, việc còn lại và vấn đề chuyển cho Gemini Argon. CEO duyệt bản cuối, đối chiếu phần đã cấp với số đo/ngoại lệ theo [§3.1.1](#311-điều-phối-kinh-phí-ai); không yêu cầu thợ tra dữ liệu thanh toán.

> **Cách dùng:** đặt toàn bộ nội dung này (hoặc bản tóm lược kèm quy tắc `agm` ở mục 3.2) vào `AGENTS.md` (Codex, OpenCode) và `CLAUDE.md` (Claude Code) của dự án; mỗi phiên bot khi khởi động cũng đọc tệp này. Khi giao việc, ghi "Việc cần làm: ...".

## Phần chưa xác minh (cần thử trên máy thực tế)

1. Lệnh dịch vụ khởi động cùng máy (`Task Scheduler` trên Windows hoặc `systemd` trên Linux) có tự khởi động `hc server start`, `agm daemon` và khôi phục ổn định sau khi reboot không.
2. Tên model slug chính xác của **Opus High trên `agy`** (kiểm bằng `agy models`).
3. `agy` chạy tương tác cho **Hydrogen Medium** (sửa docs) và **Gemini Argon** (sửa harness) trong `hc`: độ ổn định của `hc send` vào phiên `agy` đang mở, và cấu hình quyền ghi thư mục worktree cho `agy`.
4. `herdr-mesh` (chỉ cần nếu dùng HERDR TUI tách biệt với `herdr-core`; với đội chạy trong `herdr-core`, `agm` đã thay thế phần nhắn tin, theo dõi và điều phối).
5. Nguồn model OpenCode: mã provider thực tế của Ollama Cloud (`opencode models`), model nào gọi công cụ ổn định trong worktree, giới hạn đồng thời và giá hiện hành của Ollama Cloud.
6. GitNexus: chỉ mục đồng bộ giữa nhiều worktree, mức độ `analyze` ghi đè `AGENTS.md`/`CLAUDE.md`, thao tác làm mới thủ công cho OpenCode.
7. Các ngưỡng kinh nghiệm ở mục 1.1 (1–3 skill, thợ tối đa 2) và mục 3.4 / `providers.toml` (`ctx_warn = 50`, `ctx_rotate = 70`) — cần hiệu chỉnh theo số liệu thực tế từ `agm cost` và `agm ls`.
8. Người dùng xác nhận đã mở Go; catalog hiện có `opencode-go/deepseek-v4.1-flash` và `opencode-go/deepseek-v4-pro`. Vẫn cần qualification trên đúng môi trường worker/Reviewer và đối chiếu Console trước việc thật; chưa thử gọi API Go trong đợt này.
9. Ba model NVIDIA đã có trong catalog nhưng chưa benchmark chất lượng, tool calling, latency, phí hay phạm vi quota. Không ghi đã nghiệm thu chỉ vì có tên trong danh mục.

## Nguồn tham khảo

- `agmag` (`agm` v0.4.0): https://github.com/wosonday/agmag/ (`README_vi.md`, [docs/AGM-0.4.0-GUIDE.md](docs/AGM-0.4.0-GUIDE.md), `src/main.rs`, `src/actions.rs`, `src/branch_cmd.rs`, `src/mcp.rs`, `src/policy.rs`, `src/rotation.rs`, `src/ask.rs`, `.agents/decisions/p0-research.md`, `tools/argon_review.py`)
- GitHub Copilot CLI (khởi động và prompt `-p`): https://docs.github.com/en/copilot/get-started/cli-quickstart ; https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/run-cli-programmatically
- herdr-core (`hc`): `hc --help`, `hc <lệnh> --help`, `hc --skill`; https://github.com/herdrdev/herdr-core
- HERDR (kiến trúc TUI/core/app, attach từ xa): https://herdr.dev/app ; https://github.com/yigitkonur/awesome-herdr/blob/main/README.md
- herdr-mesh & herdr-mesh-safe (nếu dùng với TUI độc lập): https://github.com/runchr-works/herdr-mesh ; https://glama.ai/mcp/servers/pfoe5pzsjj
- GitNexus: https://github.com/abhigyanpatwari/GitNexus ; https://unpkg.com/gitnexus@latest/README.md
- Nguồn model OpenCode (Ollama, Ollama Cloud, OpenRouter): https://opencode.ai/docs/agents/ ; https://opencode.ai/docs/config.md ; https://mintlify.com/ollama/ollama/integrations/opencode ; https://openrouter.ai/docs/cookbook/coding-agents/opencode-integration
- OpenCode Go (kết nối, hạn mức dùng chung, Extra Usage, quyền riêng tư): https://opencode.ai/docs/go/
- Antigravity CLI (`agy`): `agy --help`, `agy models` (agy 1.5.10, 2026-11-18)
