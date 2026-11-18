# Chỉ dẫn làm việc với đội agent (phiên bản 3.2: Claude + Codex + OpenCode + Google Gemini + HERDR + herdr-mesh)

Chỉ dẫn dùng chung cho dự án code hoặc việc khác (tài liệu, báo cáo, phân tích). Quy tắc riêng của dự án (`CLAUDE.md`, `AGENTS.md`) luôn ưu tiên hơn chỉ dẫn này.

> **Cập nhật 3.2 (2026-11-18):** model Google nhận vai Tìm kiếm/research (Gemini qua Antigravity CLI `agy`) và vai Media mới (ảnh 2D, tài nguyên 3D, video qua API) — mục 1, 2.2; cách cài/nâng cấp OpenCode v2 (`@opencode/cli`, tự cập nhật, bẫy dịch vụ nền trên Windows) và nơi v2 lưu đăng nhập — mục 2.1. Với MATHY-AI, bản vận hành chính thức nằm ở `HARNESSING.md` §5.3, §5.7.

> **Cập nhật 3.1 (2026-11-17, bổ sung 2026-11-18):** thêm mục 4.2.1, gồm kết quả chạy `hc` (herdr-core 0.1.21) trên máy thật Windows 11: lệnh, dạng JSON, sự kiện, quy tắc tên; bổ sung mục 4.3 và phần "Chưa xác minh". Chi tiết về bot (template, script, dọn dẹp) nằm ở [HERDR-CORE-BOT.md](HERDR-CORE-BOT.md).

## 0. Tóm tắt mô hình

- **Mỗi phiên OpenCode = một lập trình viên riêng**, làm trên một git worktree riêng, nên nhiều feature chạy song song mà không đè lên nhau.
- **Việc cơ khí** (viết code theo đặc tả, sửa lỗi nhỏ, chạy test, tìm kiếm, đổi tên, cập nhật tài liệu) giao cho OpenCode. Model của từng phiên có thể đổi bất cứ lúc nào theo yêu cầu của Codex hoặc Opus.
- **Kiến trúc sư** (Opus 5.5 Extra hoặc Fable 5.2) quyết định hướng đi và rủi ro.
- **Reviewer** (Opus 5.5 High) duyệt kết quả.
- **Codex** là kỹ sư cố vấn và **quản lý các phiên OpenCode**: giao việc, theo dõi, gỡ vướng, đổi model/phiên.
- **Mọi agent ghi nhật ký và lưu tệp `.md` ngay trên nhánh đang làm**, commit cùng với code, và kiểm các thay đổi bằng git trước khi bàn giao (mục 3.3).
- Các agent trao đổi qua **herdr-mesh** (máy chủ MCP bọc CLI của herdr). Các phiên được chạy và quan sát qua **HERDR TUI** (người dùng điều khiển) và **herdr-core** (bot chạy nền).

### 0.1. Kiến trúc tổng thể

```
                 HERDR (TUI cho người / core cho bot)
                              |
                      HERDR-MESH (MCP)
                              |
              ORCHESTRATOR (Kiến trúc sư + Codex quản lý)
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
   Research Agent       Developer Agent      Reviewer Agent
   (Tìm kiếm)           (Thợ cơ khí)         (Reviewer)
          |                   |                   |
   model nhanh/tra cứu   model code (Codex      Opus High
   (vd. Gemini)          hoặc model OpenCode)   (GPT: ý kiến thứ hai)
          |                   |                   |
          +-------------------+-------------------+
                              |
              GIT WORKSPACE (mỗi phiên một worktree + nhánh)
                              |
               TEST / VALIDATION (Audit: test, build, lint)
                              |
               FINAL REPORT (Codex tổng hợp, mục 8)
```

Cách đọc sơ đồ:

1. **HERDR** là nơi chạy và quan sát mọi phiên; **herdr-mesh** là kênh liên lạc duy nhất giữa các agent (mục 3.2).
2. **Orchestrator** gồm hai vai đã định nghĩa ở mục 1: Kiến trúc sư (phương án, rủi ro, tiêu chí) và Codex (chia việc, giao việc, đổi model). Orchestrator không tự làm phần việc chính.
3. **Ba nhánh làm việc** ứng với các vai ở mục 1:
   - *Research Agent* = vai Tìm kiếm (chỉ đọc). Dùng **model Google** (Gemini) qua Antigravity CLI `agy` cho tìm kiếm web/research; tìm trong mã của repo có thể dùng OpenCode `explore` với model rẻ (mục 2.2).
   - *Developer Agent* = vai Thợ cơ khí. Có thể là phiên OpenCode ở bậc nào tùy mức khó; với việc khó, Codex có thể mở thêm một phiên Codex CLI trong worktree riêng như một thợ bậc Mạnh (Codex vẫn không sửa code của thợ khác).
   - *Reviewer Agent* = vai Reviewer. Mặc định Opus High. Khi cần ý kiến độc lập (việc chạm bảo mật/dữ liệu, hoặc hai lần CHƯA ĐẠT liên tiếp), thêm một phiên GPT duyệt song song; kết luận cuối vẫn thuộc Reviewer Opus High và Kiến trúc sư.
4. **Git workspace:** mọi kết quả đi qua nhánh/worktree; không agent nào ghi thẳng vào nhánh chung.
5. **Test / Validation** là cổng Audit ở mục 6; chưa đạt thì quay lại Developer Agent (lỗi chuyển nguyên văn).
6. **Final report** theo mẫu mục 8.

## 1. Vai trò và model

| Cấp | Vai | Model đề xuất | Công cụ | Quyền | Việc |
|---|---|---|---|---|---|
| 1 | Kiến trúc sư | Opus 5.5 Extra hoặc Fable 5.2 | Claude Code (`/model`) | Chỉ đọc | Phương án, rủi ro, tiêu chí đạt; chẩn đoán lỗi khó; đánh giá SẴN SÀNG trước phát hành |
| 2 | Reviewer | Opus 5.5 High | Claude Code | Chỉ đọc | Duyệt độ đúng, phạm vi, quy ước; báo ĐẠT/CHƯA ĐẠT, lỗi theo mức Nghiêm trọng/Lớn/Nhỏ kèm vị trí và cách sửa |
| 2 | Quản lý kỹ thuật (Codex) | Codex (model mạnh nhất sẵn có) | Codex CLI | Đọc, ghi hạn chế (chỉ tệp điều phối, không sửa code của thợ) | Biến phương án của Kiến trúc sư thành đầu việc cụ thể; giao việc và giám sát các phiên OpenCode; cố vấn kỹ thuật; quyết định đổi model/phiên; tích hợp (merge) sau khi Audit đạt |
| 3 | Thợ cơ khí | Do Codex chọn theo mức khó (xem mục 2) | OpenCode trong worktree riêng | Sửa trong phạm vi được giao | Viết/sửa code hoặc nội dung đúng đặc tả; báo đã đổi gì và đã tự kiểm gì |
| 4 | Tìm kiếm | **Google Gemini** (`gemini-3.8-flash` nhanh, `gemini-4-argon` sâu) | Antigravity CLI `agy --mode plan --sandbox`; tìm trong repo: OpenCode `explore` | Chỉ đọc | Tìm mã, nguồn, số liệu; trả danh sách vị trí kèm bằng chứng (URL hoặc tệp:dòng) |
| 4 | Media | **Google** (Gemini Image / Nano Banana, Gemini Omni) | API (OpenRouter hoặc Gemini API) qua script | Chỉ ghi vào thư mục media tạm | Tạo ảnh 2D, ảnh khái niệm cho tài nguyên 3D, video theo đặc tả (mục 2.2) |
| 4 | Audit | Model nhanh, rẻ | OpenCode (worktree riêng) | Chạy lệnh, không sửa mã nguồn | Chạy test/build/lint hoặc đối chiếu số liệu, mẫu, chính tả; báo ĐẠT HẾT/CHƯA ĐẠT |

Ghi chú:

1. Tên model cụ thể của OpenCode do người dùng cấu hình trong `opencode.json` (định dạng `nhà-cung-cấp/model`). Chỉ dẫn này chỉ quy định **bậc** (nhanh / vừa / mạnh), không cố định tên.
2. Mỗi vai của OpenCode nên được khai báo thành một agent trong `.opencode/agents/<tên>.md` với trường `model` và quyền (`edit`, `bash`) riêng. Như vậy đổi model chỉ cần sửa một dòng. (Repo MATHY-AI hiện dùng thư mục `.opencode/agent/`, số ít; theo đúng thư mục mà bản OpenCode đang cài nhận ra.)

### 1.1. Skill theo vai

Skill nói **cách làm**; tệp tác vụ nói **làm gì**. Khi mâu thuẫn, quy tắc dự án và `tasks/<ID>.md` thắng.

**Hạn mức khi khởi tạo một phiên (bắt buộc):**

1. Mỗi phiên khi khởi tạo chỉ nạp **1 đến 3 skill**.
2. **Thợ cơ khí tối đa 2 skill.**
3. Cần skill khác thì **thay** skill cũ (hoặc mở phiên mới), không cộng dồn.
4. Skill do Codex (hoặc Kiến trúc sư) chọn theo loại việc và ghi vào trường `skills:` trong `.agents/tasks/<ID>.md`, ví dụ `skills: test-driven-development, verification-before-completion`. Phiên chỉ dùng đúng các skill đã ghi.
5. Không nạp skill kiểu "phải gọi skill trước mọi hành động" cho thợ, Audit, Tìm kiếm và bot; chúng kéo thêm skill thiết kế và hỏi đáp vào việc cơ khí, và có thể làm phiên chạy nền treo chờ người trả lời.

| Vai | Số skill khi khởi tạo | Gợi ý (chọn theo giai đoạn) |
|---|---|---|
| Kiến trúc sư | 1 đến 3 | `brainstorming` (giai đoạn hiểu yêu cầu), `system-design` hoặc `architecture` (giai đoạn thiết kế/ghi quyết định); đổi skill khi sang giai đoạn khác |
| Codex quản lý | 1 đến 3 | `writing-plans`, `dispatching-parallel-agents`, `using-git-worktrees`; `testing-strategy` hoặc `requesting-code-review` khi cần, thay cho skill không còn dùng |
| Reviewer | 1 đến 2 | `code-review`, `verification-before-completion` |
| Thợ cơ khí | **1 đến 2** | Xem bảng loại việc bên dưới |
| Audit | 0 đến 1 | `verification-before-completion` |
| Tìm kiếm | 0 đến 1 | Skill "exploring" của GitNexus (nếu dùng) |
| Bot | 0 | Chỉ cần `hc` |

**Chọn skill cho thợ theo loại việc (tối đa 2):**

| Loại việc | Skill |
|---|---|
| Thêm tính năng, có đặc tả rõ | `test-driven-development` + `verification-before-completion` |
| Sửa lỗi | `systematic-debugging` + `verification-before-completion` |
| Sửa theo kết quả duyệt (CHƯA ĐẠT) | `receiving-code-review` + `verification-before-completion` |
| Việc cơ khí đơn giản (đổi tên, định dạng, tài liệu) | 1 skill hoặc không có |

**Cách gắn và kiểm soát:**

1. Giữ bộ skill chung trong repo (một nguồn); OpenCode đọc được `.opencode/skills`, `.claude/skills`, `.agents/skills`. **[KIỂM]** đường dẫn skill của Codex.
2. Giới hạn theo vai bằng danh sách cho phép trong chỉ dẫn mở đầu (phần thân template) và trường `skills:`; nếu công cụ có cấu hình quyền skill theo từng agent thì dùng thêm. **[KIỂM]** với OpenCode.
3. Script giao việc từ chối đầu việc có quá 2 skill cho thợ (xem `HERDR-CORE-BOT.md`, mục 1.5).
4. Kiểm chứng: chạy cùng một đầu việc mẫu có và không có skill; giữ skill nào làm giảm số lần CHƯA ĐẠT hoặc số lượt sửa lại. Ngưỡng 1 đến 3 và tối đa 2 là kinh nghiệm, cần hiệu chỉnh theo kết quả thật.

## 2. Bậc model cho thợ OpenCode và cách đổi

| Bậc | Dùng khi | Ví dụ |
|---|---|---|
| Nhanh | Việc lặp lại, rõ ràng, rủi ro thấp | Tìm kiếm, chạy test/lint, đổi tên, định dạng, cập nhật tài liệu |
| Vừa | Việc code thông thường có đặc tả rõ | Thêm endpoint, viết test, refactor cục bộ |
| Mạnh | Việc khó trong phạm vi hẹp, hoặc phiên vừa thất bại ở bậc thấp | Lỗi logic phức tạp, đa tệp, tối ưu hiệu năng |

Quy tắc đổi:

1. Codex hoặc Opus được **yêu cầu đổi model hoặc mở phiên mới** khi: thợ sửa 2 lần chưa đạt; việc rõ ràng khó hơn dự kiến; hoặc việc dễ hơn dự kiến (hạ bậc để tiết kiệm).
2. Khi đổi model, giữ nguyên worktree và nhánh; giao lại bằng bản tóm tắt (đã làm gì, còn gì, lỗi nguyên văn) ghi vào tệp tác vụ (mục 3.2) rồi báo qua herdr-mesh.
3. Chỉ Codex hoặc Opus được đổi model của thợ. Thợ không tự đổi.

### 2.1. Nguồn cung cấp model cho thợ cơ khí (OpenCode, Ollama, OpenRouter)

OpenCode là phần mềm chạy thợ; model đến từ các **nhà cung cấp (provider)** cấu hình trong `opencode.json`. Khóa API nhập bằng `/connect` hoặc `opencode auth login`, không nằm trong repo. Mã model có dạng `provider_id/model_id`.

**Cài và cập nhật OpenCode (đã kiểm 2026-11-18, Windows 11):**

1. Cài bản v2 bằng `npm install -g @opencode/cli`. Gói `opencode-ai` trên npm là dòng **v1 cũ**; trình cài bằng `curl` cũng có thể để lại bản v1 ở `~/.opencode/bin`. Kiểm bằng `opencode --version` (phải là 2.x) trong **mọi** shell (PowerShell, Git Bash).
2. Bật tự cập nhật: thêm `"update": "auto"` vào `~/.config/opencode/opencode.json` (giá trị khác: `"notify"`, `"disable"`).
3. Trên Windows, **thoát hẳn OpenCode trước khi nâng cấp**: dịch vụ nền `opencode serve --service` giữ tệp `.exe`, làm `opencode upgrade` / `npm i -g` treo và có thể xóa mất lệnh `opencode`. Nâng cấp cũng dừng mọi phiên thợ đang chạy.
4. v2 lưu thông tin đăng nhập trong SQLite `~/.local/share/opencode/opencode.db` (xem `opencode debug paths`), **không còn** `auth.json`. Script nào cần biết provider đã đăng nhập phải đọc `opencode auth list` (hoặc tệp khai báo riêng), không đọc `auth.json`.

**Ba nguồn:**

| Nguồn | Cách nối | Ưu | Nhược / lưu ý |
|---|---|---|---|
| **Ollama chạy cục bộ** | Khai báo provider `ollama`, gói `@ai-sdk/openai-compatible`, `baseURL` là `http://localhost:11434/v1`, liệt kê model trong `models`; hoặc chạy `ollama launch opencode` để tự cấu hình | Không tốn phí token; mã không rời máy | Phụ thuộc phần cứng. Ollama khuyến nghị cửa sổ ngữ cảnh tối thiểu 64k cho OpenCode; nếu gọi công cụ lỗi, tăng `num_ctx` |
| **Ollama Cloud** | Lấy khóa API tại ollama.com (Settings, Keys), chạy `opencode auth login` rồi chọn Ollama Cloud; hoặc `ollama launch opencode`. Endpoint `https://ollama.com`, biến môi trường `OLLAMA_API_KEY`. Model cloud có hậu tố `:cloud` | Model lớn không cần GPU cục bộ; Ollama gợi ý `glm-4.7:cloud` cho OpenCode | Mã gửi lên dịch vụ ngoài; có giới hạn số model cloud chạy đồng thời theo gói (xem bên dưới) |
| **OpenRouter** | `/connect` rồi tìm OpenRouter; thêm model bằng slug dưới `provider.openrouter.models` trong `opencode.json`; mã dùng là `openrouter/<slug>` | Một khóa truy cập nhiều model; chọn được nhà cung cấp hạ nguồn qua `options.provider` của từng model | Mã gửi lên dịch vụ ngoài; chất lượng và giá phụ thuộc model, nhà cung cấp hạ nguồn |

**Gói và giới hạn của Ollama Cloud (biến động, phải xem lại trên ollama.com/pricing):** các trang tôi đọc không thống nhất. Một số nêu số model cloud chạy đồng thời theo gói (Free 1, Pro 3, Max 10); một số nêu Ollama đã chuyển sang tính theo token từ 31/08/2026, gói Pro 20 USD kèm 60 USD sử dụng, Max 100 USD kèm 300 USD, và bậc 0 USD trả theo mức dùng. Vì thế `MAX_WORKERS` (xem `HERDR-CORE-BOT.md`) **không được vượt giới hạn đồng thời của gói đang dùng**, nếu giới hạn đó còn áp dụng.

**Gán nguồn cho bậc model (mục 2):** đây là gợi ý, tên model phải kiểm theo danh mục hiện hành vì thay đổi liên tục.

| Bậc | Nguồn gợi ý |
|---|---|
| Nhanh | Ollama cục bộ (model nhỏ) hoặc model rẻ trên Ollama Cloud / OpenRouter |
| Vừa | Ollama Cloud hoặc model code trên OpenRouter |
| Mạnh | Model mạnh trên OpenRouter (hoặc Ollama Cloud nếu có), hoặc nâng lên Codex/Claude theo mục 2 |

**Khai báo trong repo (mẫu, thay bằng model có thật):**

```
# opencode.json (không chứa khóa API)
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": { "baseURL": "http://localhost:11434/v1" },
      "models": { "qwen3-coder": { "name": "qwen3-coder" } }
    },
    "openrouter": {
      "models": { "qwen/qwen3-coder": {} }
    }
  }
}
```

```
# .opencode/agents/worker-fast.md   (tương tự worker-mid.md, worker-strong.md)
---
description: Thợ bậc nhanh
mode: subagent
model: ollama/qwen3-coder
---
```

Với Ollama Cloud, đừng viết tay cấu hình; chạy `opencode auth login` hoặc `ollama launch opencode`, rồi lấy mã chính xác bằng `opencode models` (**[KIỂM]** mã provider thực tế).

**Quy tắc sử dụng:**

1. **Đổi nguồn do Codex hoặc Opus quyết định**, không do thợ (mục 2, quy tắc đổi). Khi nguồn bị giới hạn tốc độ hoặc lỗi, Codex đổi sang nguồn khác cùng bậc, giữ nguyên worktree, và ghi vào nhật ký.
2. **Dữ liệu nhạy cảm:** đầu việc chạm bảo mật hoặc dữ liệu (mục 5, quy tắc 2) chỉ dùng model cục bộ, hoặc phải được người dùng đồng ý trước khi gửi mã lên nguồn cloud.
3. **Khóa API:** chỉ lưu trong kho đăng nhập của OpenCode (`opencode auth login`) hoặc biến môi trường (`OLLAMA_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`) của dịch vụ bot; không đưa vào repo, tệp tác vụ hay nhật ký.
4. **Chi phí:** người dùng quyết định ngân sách (mục 3.1); bot giới hạn số thợ đồng thời và số phiên theo `bot.env`.
5. **Chọn model theo năng lực gọi công cụ:** thợ phải gọi công cụ ổn định (sửa tệp, chạy lệnh). Trước khi dùng model mới cho thợ, chạy thử một đầu việc mẫu: sửa một tệp trong worktree, chạy test, ghi nhật ký, commit. Model không qua thử nghiệm thì không được giao việc thật.
6. Tệp tác vụ có thể ghi trường `tier: nhanh | vừa | mạnh`; bot chọn template tương ứng (`worker-fast`, `worker-mid`, `worker-strong`).

### 2.2. Model Google: tìm kiếm/research, ảnh 2D/3D, video

Người dùng giao cho model Google ba trách nhiệm: **tìm kiếm và research thông tin**, **tạo ảnh** (kể cả khi cần dựng tài nguyên 2D/3D) và **làm video**. Hai đường gọi khác nhau:

| Trách nhiệm | Gọi bằng | Model (kiểm 2026-11-18) | Ghi chú |
|---|---|---|---|
| Tìm kiếm / research | Antigravity CLI `agy` (công cụ `search_web`) | `gemini-3.8-flash-{low,medium,high}` (nhanh), `gemini-4-argon-{low,medium,high}` (tổng hợp sâu), `gemini-4-hydrogen-{low…xhigh}` (suy luận nặng), `gemini-pro-orchestrator-g1-pro` (điều phối nhiều agent con) | Đã chạy thật. Danh sách theo gói tài khoản Google: xem bằng `agy models` |
| Ảnh 2D | HTTP API: OpenRouter (`OPENROUTER_API_KEY`) hoặc Gemini API (`GEMINI_API_KEY`) | `google/gemini-nano-banana-2.1`, `google/gemini-3-pro-image`, `google/gemini-3.1-flash-image` | `agy` CLI **không** có công cụ tạo ảnh (Antigravity IDE thì có, dùng tay) |
| Video | Như trên | `google/gemini-omni-1.2-flash` (OpenRouter); Veo cần Gemini API hoặc Vertex AI | Tính tiền theo lượt, đắt |
| 3D | Không có model Google tạo 3D trực tiếp | (a) Gemini tạo ảnh khái niệm → Space image-to-3D trên Hugging Face; (b) Gemini viết mã three.js/glTF | Chọn theo việc |

**Research — mẫu lệnh (không cần người, đã kiểm):**

```bash
cd <thư-mục-tạm-ngoài-repo>
agy --model gemini-4-argon-medium --mode plan --sandbox --print-timeout 600s --output-format json \
  -p "<câu hỏi>. Mỗi kết luận kèm URL nguồn. Không sửa tệp." > research.json
# research.json: {"status":"SUCCESS","response":"…","usage":{…},"conversation_id":"…"}
```

**Quy tắc riêng cho model Google:**

1. **Research là gợi ý, không phải sự thật.** Lần thử 2026-11-18, Gemini báo sai phiên bản một gói npm dù kèm đúng URL. Codex/Kiến trúc sư đối chiếu mọi con số, phiên bản, giá với nguồn gốc (lệnh `npm view`, trang chính thức) trước khi đưa vào tệp tác vụ.
2. `agy` có quyền riêng, **không** đọc quyền của agent OpenCode. Luôn chạy `--mode plan --sandbox`, ở thư mục tạm ngoài repo; không bao giờ `--dangerously-skip-permissions`.
3. Tìm ra danh sách model ảnh/video: OpenCode chỉ liệt kê model văn bản; dùng `https://openrouter.ai/api/v1/models` và lọc `architecture.output_modalities` chứa `image` hoặc `video`.
4. Tạo media: tệp tác vụ ghi **số lượt tạo tối đa**; thử bằng model flash-image trước model pro. Kết quả lưu ở thư mục tạm; chỉ tệp đã chọn mới commit, qua nhánh của phần sở hữu thư mục đích.
5. Dữ liệu gửi đi theo đúng quy tắc mục 2.1 quy tắc 2: không bí mật, không dữ liệu khách.

## 3. Điều phối và giao tiếp

### 3.1. Trách nhiệm

- **Người dùng:** quyết định về nghiệp vụ, quyền, dữ liệu, chi phí; phê duyệt phát hành.
- **Kiến trúc sư:** hiểu yêu cầu, lập phương án và tiêu chí đạt, không tự làm phần việc chính.
- **Codex:** chia phương án thành đầu việc, giao việc một lần cho đủ (mục tiêu, phạm vi được sửa, ràng buộc, tiêu chí đạt, mẫu báo cáo), theo dõi tiến độ, gỡ vướng cho thợ.
- **Mỗi tệp/phần chỉ một phiên sửa tại một thời điểm.** Codex chịu trách nhiệm phân chia để các worktree không chồng phạm vi.
- Công cụ không tạo được phiên riêng thì một AI tự đóng lần lượt từng vai, đúng thứ tự.

### 3.2. Giao tiếp bằng herdr-mesh

herdr-mesh là một máy chủ MCP bọc CLI của herdr thành các công cụ MCP, để agent đọc pane của agent khác, bàn giao ngữ cảnh, phối hợp và mở agent mới. Nó không gắn với một loại agent cụ thể. Vì vậy:

1. **Cài đặt:** cài toàn cục rồi chạy `herdr-mesh install` để công cụ tự dò agent và đăng ký. Mỗi agent là một MCP client riêng nên phải đăng ký cho từng agent (Claude Code, Codex, OpenCode). Với Claude Code có thể dùng `claude mcp add -s user herdr-mesh herdr-mesh`.
2. **Phạm vi:** herdr-mesh chỉ nối các agent **đang chạy trong cùng một herdr** (xem mục 4.3). Đích đến là **tên agent đang chạy** hoặc **mã pane**.
3. **Tên agent:** chỉ gồm chữ thường, số, `-`, `_`, bắt đầu bằng chữ cái, tối đa 32 ký tự. Quy ước: `arch`, `review`, `codex-mgr`, `w-<feature>-<số>` (thợ), `bot-<sự kiện>` (bot). `hc run --name` cũng áp đúng giới hạn này (đã kiểm), nên **mã việc `<ID>` phải viết thường** để tên `w-<ID>` hợp lệ.
4. **Cách gửi:** dùng công cụ `herdr_relay` (gửi và nhấn gửi trong một bước), không tự gõ vào pane rồi quên xác nhận gửi.
5. **Trước khi gửi:** kiểm tra trạng thái agent đích. Nếu đang `working` thì chờ `idle`, `done` hoặc `blocked`; không gõ chen vào prompt đang hoạt động. Mỗi lần chỉ gửi một tin ngắn, một việc. Khi cần đọc kết quả, chỉ lấy phần trả lời mới, không đọc cả pane, để tiết kiệm ngữ cảnh.
6. **Thông tin bền vững ghi vào tệp, không chỉ nằm trong tin nhắn.** Tin nhắn chỉ là tín hiệu và con trỏ. Đặc tả, quyết định, kết quả kiểm, tóm tắt bàn giao ghi vào `.agents/tasks/<ID>.md` trong worktree (hoặc nhánh) và tin nhắn chỉ trỏ tới tệp đó. Lý do: tài liệu công khai tôi tra được không nói herdr-mesh lưu lịch sử tin nhắn bền vững.
7. **Khóa ghi (tùy chọn):** bản fork `herdr-mesh-safe` bổ sung "lease" cho người điều khiển, reviewer và writer. Cơ chế này phù hợp với quy tắc "mỗi tệp/phần chỉ một phiên sửa"; nên cân nhắc nếu cần thực thi quy tắc bằng công cụ thay vì bằng kỷ luật.

Mẫu tin nhắn bắt buộc (ngắn, một tin một việc):

```
[LOẠI] GIAO | BÁO CÁO | LỖI | HỎI | CHẶN | ĐẠT | CHƯA ĐẠT
[ID] task-123    [NHÁNH] feat/ten-feature
[TỆP TÁC VỤ] .agents/tasks/task-123.md
[TÓM TẮT] một đến hai câu
[KẾT QUẢ KIỂM] số đếm (với tin BÁO CÁO)
```

Lỗi do Audit/Reviewer tìm ra được chuyển **nguyên văn** (qua tệp tác vụ) cho đúng thợ đã làm, thông qua Codex.

### 3.3. Sổ ghi chép trên nhánh và kiểm thay đổi kiểu git

Nguyên tắc: **git là nguồn sự thật về "đã đổi gì"; tệp `.md` ghi "vì sao" và "đã kiểm gì"**. Cả hai nằm trên cùng nhánh, đi cùng nhau.

**Cấu trúc thư mục (mỗi tệp theo mã việc `<ID>` nên không xung đột khi merge):**

```
.agents/
  tasks/<ID>.md         # đặc tả: mục tiêu, phạm vi sửa, ràng buộc, tiêu chí đạt   (Codex viết)
  log/<ID>.md           # nhật ký làm việc, chỉ thêm, không sửa cũ                 (thợ viết)
  reviews/<ID>-<n>.md   # kết quả duyệt lần n: ĐẠT/CHƯA ĐẠT, lỗi, vị trí, cách sửa   (Reviewer viết)
  decisions/<ID>.md     # quyết định thiết kế, rủi ro, lý do                      (Kiến trúc sư/Codex viết)
  reports/<ID>.md       # báo cáo cuối của nhánh (mục 8)                           (Codex viết)
```

**Quy tắc ghi:**

1. **Mỗi tệp một người ghi** (cột bên phải ở trên), đúng nguyên tắc "một phần, một người sửa". Thợ không sửa `tasks/`; muốn đổi đặc tả thì ghi đề xuất vào `log/` và báo Codex.
2. **Nhật ký chỉ thêm.** Sai thì thêm mục đính chính bên dưới, không xóa hay viết lại mục cũ.
3. **Commit sớm và nhỏ.** Mỗi bước có ý nghĩa (xong một phần, trước khi thử hướng rủi ro, trước khi bàn giao) là một commit, **gồm cả code và mục nhật ký tương ứng**. Thông điệp commit bắt đầu bằng `<ID>:`.
4. **Cấp quản lý cũng ghi:** Kiến trúc sư ghi `decisions/`, Codex ghi `tasks/`, `reports/` và các lần đổi model/phiên vào nhật ký điều phối, Reviewer ghi `reviews/`. Tất cả commit trên nhánh mà họ đang đứng.
5. Không ghi bí mật (khóa, mật khẩu, dữ liệu cá nhân) vào các tệp này.

**Mẫu một mục nhật ký:**

```
## 2026-11-17 21:05 · w-login-1 · bước 2/4
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
5. **Codex** kiểm lại các bước trên trước khi tích hợp. Khi có lỗi, chuyển nguyên văn qua `reviews/` hoặc nhật ký, rồi quay lại thợ.
6. Muốn xem lịch sử một việc, dùng `git log -- .agents/log/<ID>.md` hoặc `git log --oneline <nhánh>`; muốn hoàn tác một bước, dùng `git revert` và ghi mục đính chính.

Khi tích hợp vào nhánh chung, giữ thư mục `.agents/` trong repo theo mặc định; Codex có thể quyết định loại khỏi bản phát hành nếu không muốn đưa ra ngoài.

### 3.4. Vòng đời của thợ: ngắn hạn theo đầu việc, ngữ cảnh nằm trong tệp

Vì trạng thái đã nằm trong `.agents/` và git, thợ là **thay thế được**; mặc định sống ngắn.

| Vai | Vòng đời |
|---|---|
| Tìm kiếm, Audit | Sinh rồi diệt theo từng yêu cầu, không giữ trạng thái |
| Thợ cơ khí | Sống trong phạm vi một đầu việc; chỉ giữ qua nhiều đầu việc khi cùng feature và cùng vùng mã |
| Reviewer | Phiên mới cho mỗi lần duyệt (giữ độc lập); khi duyệt lại, đưa kết quả duyệt trước bằng tệp |
| Bot (herdr-core) | Sống lâu nhưng ngữ cảnh rất nhỏ, chỉ điều phối sự kiện và sinh thợ |
| Kiến trúc sư, Codex | Sống lâu theo feature, định kỳ nén ngữ cảnh, quyết định ghi vào tệp |

**Diệt thợ và thay bằng phiên mới (giữ nguyên worktree và nhánh) khi:** đầu việc xong hoặc đã tích hợp; thợ sửa 2 lần chưa đạt (phiên mới có góc nhìn sạch, kèm nâng bậc model); ngữ cảnh đã đầy quá nửa (ngưỡng kinh nghiệm, cần điều chỉnh theo thực tế); đổi model hoặc phạm vi; thợ lặp lại sai lầm cũ hoặc dựa vào giả định đã lỗi thời.

**Bàn giao cho phiên mới:** trước khi diệt, thợ cũ (hoặc Codex) ghi vào nhật ký: đã làm gì, còn gì, lỗi nguyên văn, quyết định đã chốt, và **commit** tất cả. Phiên mới bắt đầu bằng cách đọc `tasks/<ID>.md`, `log/<ID>.md` và `git log` của nhánh.

### 3.5. Quy tắc sinh agent phụ

1. **Chỉ Kiến trúc sư và Codex được sinh agent.** Thợ, Reviewer, Audit và bot không tự sinh. Độ sâu tối đa một cấp.
2. **Hai loại:** *subagent trong phiên* (ngắn hạn, chỉ đọc, đầu ra có giới hạn; dùng cho tìm kiếm, tóm tắt, đối chiếu) và *phiên riêng trong HERDR* (dài hơn, có worktree riêng; dùng cho việc sửa mã).
3. **Giới hạn trao đổi:** thợ chỉ nhắn cho `codex-mgr`, không nhắn nhau; việc cần phối hợp do Codex làm trung gian. Mỗi agent phụ nhận một đầu việc, bộ công cụ tối thiểu và mẫu báo cáo định sẵn.
4. **Hạn mức:** số phiên đồng thời tối đa và ngân sách token mỗi phiên (xem mục 4.2). herdr-mesh cho agent mở agent mới theo chỉ dẫn, nên nếu không giới hạn thì số phiên và chi phí dễ vượt kiểm soát; bản `herdr-mesh-safe` có lease để hỗ trợ.

### 3.6. Lớp ngữ cảnh mã nguồn: GitNexus (đã chọn)

GitNexus **không phải công cụ quản lý tác vụ**. Nó lập chỉ mục mã nguồn thành đồ thị phụ thuộc, chuỗi gọi hàm và luồng thực thi rồi đưa cho agent qua MCP. Việc quản lý tác vụ vẫn do `.agents/` và git đảm nhiệm.

**Giấy phép:** GitNexus dùng PolyForm Noncommercial. Dự án hiện tại không thương mại nên được dùng. Nếu sau này dự án chuyển sang thương mại, phải xem lại giấy phép hoặc chuyển sang phương án MIT như codebase-memory-mcp.

**1. Agent đọc được**

| Agent | Mức hỗ trợ |
|---|---|
| Claude Code | MCP, skill, hook |
| Codex | MCP, skill, hook (cài hook bằng `gitnexus setup -c codex`) |
| OpenCode | MCP và skill, không hook |

**2. Cài đặt (làm một lần, trên nhánh riêng, do Codex thực hiện)**

1. Cài toàn cục để MCP khởi động nhanh và tránh quá thời gian chờ khi dùng `npx` lần đầu: `npm install -g gitnexus`.
2. Từ gốc repo: `gitnexus analyze` rồi `gitnexus setup` (tự dò Claude Code, Codex, OpenCode và ghi cấu hình MCP).
3. Với OpenCode, nếu cần cấu hình tay, khai báo trong `~/.config/opencode/config.json` mục `mcp`, máy chủ `gitnexus` kiểu `local`, lệnh `["gitnexus", "mcp"]`.
4. **Lưu ý:** `analyze` còn cài skill, đăng ký hook của Claude Code và tạo/cập nhật các tệp ngữ cảnh `AGENTS.md`, `CLAUDE.md`. Vì vậy phải chạy trên một nhánh, xem `git diff`, giữ nguyên các quy tắc của dự án, rồi mới commit (theo mục 3.3). Không để công cụ ghi đè chỉ dẫn này.
5. Có thể chạy một máy chủ dùng chung cho nhiều client bằng `gitnexus mcp --http`.

**3. Phân công dùng**

| Vai | Công cụ GitNexus nên dùng |
|---|---|
| Kiến trúc sư | `impact`, `context`, `generate_map` để đánh giá phương án và rủi ro |
| Reviewer | `detect_changes`, `impact` để kiểm phạm vi ảnh hưởng của diff |
| Thợ cơ khí | `impact` trước khi sửa; `rename` khi đổi tên; `trace` khi tìm lỗi |
| Tìm kiếm | `query`, `context` |
| Audit | Không cần |

**4. Giữ chỉ mục luôn mới**

1. OpenCode không có hook nên không tự được nhắc làm mới chỉ mục. Sau mỗi lần tích hợp nhánh vào nhánh chung, Codex (hoặc bot) chạy `gitnexus analyze`.
2. Mỗi worktree là một cây làm việc riêng: khi bot tạo worktree mới, chạy `gitnexus analyze` trong worktree đó và kiểm tra chỉ mục có đúng với nhánh đang làm không (tài liệu chính không nói rõ về worktree, chỉ nói rằng bỏ tham số `branch` thì truy vấn chỉ mục theo cây làm việc đang checkout, và có thể ghim theo nhánh bằng `--branch`).
3. Chú ý bộ nhớ khi lập chỉ mục repo lớn; nếu máy yếu, không chạy nhiều lần `analyze` đồng thời.
4. Ghi vào nhật ký (mục 3.3) mỗi lần làm mới chỉ mục và kết quả.

**5. Kiểm tra sau khi cài (làm trước khi giao việc thật):** thử ba việc trên chính repo: tìm nơi gọi một hàm, đánh giá ảnh hưởng của một thay đổi, đổi tên một ký hiệu; thực hiện từ cả Claude Code, Codex và OpenCode. Ghi kết quả vào `.agents/decisions/`.

**Phương án dự phòng:** nếu GitNexus không đạt (lệch chỉ mục giữa worktree, tốn bộ nhớ) thì thử codebase-memory-mcp (MIT) hoặc Serena (công cụ ngữ nghĩa dựa trên LSP).

## 4. HERDR: TUI cho người, core cho bot

### 4.1. HERDR TUI (người dùng điều khiển)

- Dùng để mở các phiên Claude Code, Codex, OpenCode cạnh nhau, xem trạng thái (đang chạy / bị chặn / xong) và can thiệp.
- Điều khiển từ xa: máy chủ chạy HERDR TUI; từ điện thoại dùng **Moshi** (iOS/Android) kết nối vào máy chủ rồi gắn lại (attach) phiên. HERDR TUI có chế độ attach từ xa qua SSH, phiên vẫn chạy khi ngắt kết nối.
- Phiên của Kiến trúc sư, Reviewer, Codex nên chạy ở đây để người dùng đọc và phản hồi được.

### 4.2. herdr-core (bot chạy nền)

- **Bot** là agent được cấu hình chạy liên tục, phản ứng theo sự kiện đã thiết lập trước (ví dụ: có issue mới, có yêu cầu từ người dùng, một nhánh vừa được đẩy lên, một lịch định kỳ).
- Khi có sự kiện, bot thực hiện đúng thứ tự:
  1. Tạo git worktree + nhánh mới cho đầu việc: `git worktree add ../wt-<feature> -b feat/<feature>`.
  2. Khởi động một phiên OpenCode trong worktree đó với agent và model theo đầu việc.
  3. Đặt tên agent `w-<feature>-<số>` và báo cho `codex-mgr` bằng `herdr_relay`.
  4. Khi xong hoặc bị chặn, gửi tin `BÁO CÁO` / `CHẶN`; **không tự merge**.
- Giới hạn bắt buộc cho bot chạy không người giám sát: số phiên đồng thời tối đa, giới hạn chi phí/token mỗi phiên, quyền `edit`/`bash` của OpenCode đặt rõ (chặn lệnh phá hủy, chặn ghi ngoài worktree), có cách dừng khẩn cấp.
- Bot dọn worktree sau khi nhánh đã được tích hợp hoặc bị hủy.
- Nên khảo sát trước các plugin cộng đồng đã làm đúng bước 1-2 (ví dụ `herdr-symphony`: đọc issue, tạo worktree, chạy một OpenCode agent cho mỗi issue) thay vì tự viết từ đầu.
- Đường dẫn worktree theo quy ước của dự án (ví dụ MATHY-AI dùng `../MATHY-AI.wt/<slug>`); `../wt-<feature>` ở bước 1 chỉ là mặc định. Template, script giao việc/theo dõi/dọn dẹp: xem [HERDR-CORE-BOT.md](HERDR-CORE-BOT.md).

### 4.2.1. `hc` trên máy thật (đã kiểm 2026-11-17, hc 0.1.21, Windows 11)

CLI của herdr-core là `hc`. Thử nhanh bằng ba lệnh:

```powershell
hc run --bg --name demo ping -n 600 127.0.0.1   # chạy nền, trả JSON có "address":"t10", "state":"live"
hc ls                                           # liệt kê terminal đang sống
hc read demo --lines 10                         # đọc 10 dòng cuối, không cần attach
```

Những gì đã thấy trên máy thật (khác hoặc rõ hơn tài liệu công khai):

| Điểm | Kết quả thật | Hệ quả |
|---|---|---|
| Core | Đã chạy sẵn; `hc server start\|stop\|status\|restart` tồn tại. `hc server status` trả JSON có `live`, `finished`, `uptime_ms`, `version` | Dịch vụ khởi động cùng máy có thể dùng `hc server start`; còn phải thử sau khi khởi động lại máy |
| Đầu ra | Mặc định là JSON khi đầu ra đi qua đường ống; `run` và `read` in văn bản | Script đọc được bằng `jq`/`ConvertFrom-Json` mà không cần phân tích bảng |
| Dạng `hc ls` | Một **đối tượng** `{"hidden_finished": n, "terminals": [...]}`, **không phải mảng** | Đếm thợ bằng `jq '.terminals \| length'` (đã sửa trong `dispatch.sh`, HERDR-CORE-BOT.md §1.5) |
| Quan hệ cha–con | `hc run` gọi từ trong một terminal sẽ tự gán `parent` là terminal đó (ví dụ `t3` → `t9` → `t10`); `hc get` cho thấy `die_with_parent: true` theo mặc định | Thợ phải sống sót khi bot khởi động lại → bắt buộc `--outlive-parent` |
| Báo trạng thái | Terminal Claude Code có `reported: true`, `status: {app: "claude-code", state: "working", msg: "..."}`. Chương trình thường (`ping`, `pwsh`) có `reported: false`, `status: null` | Claude Code tự báo trạng thái, nên `hc events`/`hc wait` dùng được. Với OpenCode, Codex: chưa kiểm, cần `ready: quiet` hoặc chuỗi đánh dấu |
| Tên terminal | `--name` chỉ nhận 1–32 ký tự `a-z 0-9 - _`, không chữ hoa | Mã việc phải viết thường (`test-1`, không phải `TEST-1`); `dispatch.sh` kiểm trước khi chạy |
| Vị trí | Terminal có trường `where` (ví dụ `"MATHY-AI / 1"`); `demo` nhận `where` của cha. Terminal chạy kèm `--label` thì sự kiện `created` chưa thấy `where` | Biết thợ đang nằm ở workspace/tab nào; đừng dựa vào `where` để lọc, hãy dùng `--label` |
| Sự kiện | `hc events --json`: dòng đầu là ảnh chụp `{"channel", "seq", "terminals"}`; các dòng sau theo dạng JSON-RPC `{"method":"event","params":{"type":"created"\|"finished", "terminal", "seq", "data"}}`. Sự kiện `finished` có `data: {exit_code, reason, signal}` | `watch.sh` đọc `.params.type`; xử lý cả `finished` (thợ thoát), không chỉ trạng thái |
| Template | `hc templates` trả `{"templates": []}` | Phải tự tạo `worker-fast`, `worker-mid`, `worker-strong`, `auditor`, `researcher` theo HERDR-CORE-BOT.md §1.4 |
| Dọn dẹp | `hc kill <t>` kết thúc; `hc rm <t>` gỡ terminal đã kết thúc (trả `{"removed":"t10"}`); `hc ls --all` thấy cả terminal đã kết thúc (có `exit_code`, `reason`); `hc run --rm` tự gỡ ngay sau khi thoát | Dùng `--rm` cho lệnh ngắn (Audit, Tìm kiếm). **Không** dùng cho thợ, vì sau khi thợ thoát còn cần `hc read` để xem lỗi |
| Báo khi con kết thúc | Khi terminal con thoát, `hc` tự gõ vào agent cha một ghi chú `<hc>t10 demo exited (exit 0). Last lines: ... Read: hc read t10</hc>` kèm các dòng cuối | Agent cha (Codex quản lý, bot) biết thợ đã thoát mà không cần chạy vòng theo dõi. Tắt cho một terminal bằng `hc run --no-notify`, hoặc tắt hẳn bằng `notes = false` trong `config.toml` |

Các lệnh khác có trong `hc --help` mà tài liệu cũ chưa nêu:

- `hc wait <t>`: chờ terminal ngừng làm việc (`--children all|any` chờ các agent con). **Dùng thay cho `sleep`.** `--output X` chờ đến khi in ra X, nhưng `--help` ghi rõ nó **dành cho chương trình, không dành cho agent**. Muốn biết một agent đã xong thì dựa vào trạng thái nó báo, hoặc cho nó thoát rồi bắt sự kiện `finished`.
- `hc interrupt <t>`: nhấn phím dừng rồi báo kết quả. `hc keys <t> enter|esc|up|ctrl+c`: gửi phím.
- `hc put <t> <file>`: gửi một tệp sang cạnh terminal đích.
- `hc exec [--on m] <cmd>` và `hc file read|write|edit`: chạy lệnh hoặc sửa tệp mà không cần mở terminal (cũng dùng được trên máy từ xa).
- `hc keep <t>`: tự thay bằng shell khi chương trình bị mất. `hc label <t> k=v`: gắn nhãn sau khi đã chạy.
- Cấu hình `~/.config/herdr-core/config.toml`: `notes = false` để `hc` không tự gõ ghi chú vào agent cha; `draft_wait` là số giây hoãn tin gửi đến trong lúc người dùng đang gõ dở.

**Lưu ý Windows:** các script mẫu trong HERDR-CORE-BOT.md viết cho bash/`jq`/`systemd`/`flock`. Máy kiểm chưa có `jq` (`winget install jqlang.jq`). Trên Windows cần viết lại bằng PowerShell và dùng Task Scheduler thay cho `systemd` (đề xuất, chưa thử).

### 4.3. Lưu ý quan trọng về phạm vi giao tiếp

HERDR TUI và herdr-core (cũng như ứng dụng desktop xây trên core) hiện **không dùng chung backend**: agent chạy ở bên này không hiện ở bên kia. Vì herdr-mesh hoạt động qua CLI của herdr, **hai bên không nhắn tin cho nhau được bằng herdr-mesh**. Cách xử lý, theo thứ tự ưu tiên:

1. **Cùng một herdr cho toàn đội (nên thử trước):** đặt các agent cần trao đổi (Kiến trúc sư, Reviewer, Codex, thợ) vào cùng một herdr, rồi xác minh bot có tạo phiên được ở đó không.
2. **Hai bên tách biệt, bàn giao qua git và tệp tác vụ:** bot ghi `.agents/tasks/<ID>.md`, đẩy nhánh; Codex trong TUI đọc nhánh/tệp và giao việc tiếp. Chậm hơn nhưng không phụ thuộc kênh nhắn tin.
3. Không dựa vào việc TUI và core hợp nhất trong tương lai; kiểm tra phiên bản khi nâng cấp.

**Quan sát 2026-11-17:** trên máy chạy core 0.1.21, `hc ls` thấy cùng lúc các phiên Claude Code đang mở, các shell `pwsh` và các terminal do `hc run` tạo, mỗi cái có trường `where` là tên workspace/tab. Như vậy, trong phạm vi core, mô hình "cả đội trong core" (HERDR-CORE-BOT.md §1.8, mô hình A) chạy được: agent nhắn nhau bằng `hc send`, chờ bằng `hc wait`, không cần herdr-mesh. Việc HERDR TUI có thấy các terminal này không thì vẫn chưa kiểm.

## 5. Quy tắc giao việc

1. Tìm kiếm → agent Tìm kiếm. Kiểm tra → Audit. Sửa/soạn → Thợ cơ khí. Phân việc, đổi model → Codex.
2. Gọi **Kiến trúc sư** khi: đổi cấu trúc lớn; việc chạm bảo mật/dữ liệu; lỗi sửa 2 lần chưa xong (kể cả sau khi đã nâng bậc model); trước phát hành.
3. Gọi **Codex** khi: cần chia việc, chọn/đổi model, gỡ vướng kỹ thuật, tích hợp nhánh.
4. Gọi **Reviewer** sau khi Audit đạt, cho từng nhánh/phần.
5. Sau chẩn đoán của Kiến trúc sư vẫn chưa xong thì dừng và hỏi người dùng.

## 6. Cổng phát hành (làm đúng thứ tự)

**Lưu bản / commit trên nhánh worktree** → **Audit đạt hết** → **Reviewer (Opus High) đạt** → **Codex tích hợp vào nhánh chung, Audit lại trên nhánh chung** → **Xem thử (nếu có giao diện)** → **Kiến trúc sư SẴN SÀNG** → **Phát hành (người dùng phê duyệt)** → **Xác minh môi trường thật**

- Có lỗi ở bước nào thì sửa, lưu bản mới, chạy lại từ Audit.
- Kiểm không chạy được thì ghi rõ lý do, không báo là đạt.
- Trước mỗi cổng, kiểm thay đổi kiểu git theo mục 3.3 (không còn tệp chưa commit, nhật ký khớp diff, không sửa ngoài phạm vi).
- Bot và thợ không được phát hành; chỉ Codex tích hợp, chỉ người dùng phê duyệt phát hành.

## 7. Việc không phải code

Giữ nguyên đội hình và cổng. Kiến trúc sư lập dàn ý; Codex chia phần; mỗi thợ soạn một phần riêng (một worktree/tệp riêng); Tìm kiếm lấy nguồn, số liệu; Audit kiểm số liệu, mẫu, chính tả; Reviewer duyệt nội dung. "Commit" là lưu bản có số phiên bản; "phát hành" là gửi bản cuối. Mẫu người dùng đưa luôn giữ nguyên bố cục.

## 8. Báo cáo cuối

Do Codex tổng hợp và lưu vào `.agents/reports/<ID>.md` trên nhánh, ngắn gọn: đã đổi gì, ai làm (phiên nào, model nào), kết quả kiểm (số đếm), kết luận Reviewer/Kiến trúc sư, phần chưa xác minh, việc còn lại.

> **Cách dùng:** `AGENTS.md` (Codex, OpenCode) và `CLAUDE.md` (Claude Code) của dự án tóm tắt các quy tắc bắt buộc và trỏ tới tệp này; mỗi phiên bot khi khởi động cũng đọc tệp này. Khi giao việc, ghi "Việc cần làm: ...".
>
> Trong SpySWAT: tệp này nằm ở `docs/agents/AGENTS-TUTORIAL.md`, phần tóm tắt nằm ở mục "Agent team workflow" của `AGENTS.md`, mẫu tệp ở `.agents/templates/`.

## Phần chưa xác minh (cần thử trên máy thực tế)

1. ~~Lệnh/cấu hình cụ thể để herdr-core kích hoạt bot theo sự kiện.~~ **Đã kiểm một phần (mục 4.2.1):** lệnh `hc`, dạng JSON của `hc ls`/`hc get`/`hc events` (sự kiện `created`, `finished`), quan hệ cha–con, Claude Code tự báo trạng thái, `hc server`, `hc rm`, `--rm`, `--no-parent`, `--no-notify`, quy tắc tên. **Còn phải kiểm:** dạng `data` của sự kiện đổi trạng thái; OpenCode và Codex có tự báo trạng thái không; `hc wait --output` có dùng được với thợ OpenCode không; core và thợ có tự lên lại sau khi khởi động lại máy không; script bot chạy trên Windows.
2. herdr-mesh có hoạt động với herdr-core hay chỉ với HERDR TUI; và tương thích với phiên bản herdr đang dùng (có bản fork riêng cho herdr 0.9.5, ghi chú bản sửa đang chờ upstream). Nếu dùng mô hình "cả đội trong core" (mục 4.3) thì câu hỏi này không còn chặn công việc.
3. Việc herdr-mesh có nhắn tin được giữa các máy (qua attach SSH) hay chỉ trong một máy.
4. Việc tin nhắn có được lưu lại bền vững hay không (tài liệu không nêu; vì vậy mục 3.2 buộc ghi thông tin quan trọng vào tệp).
5. Cách đăng ký herdr-mesh cho OpenCode (trình cài đặt tự dò agent; cần thử xem OpenCode có được nhận không).
6. Nguồn model: mã provider thực tế của Ollama Cloud trong OpenCode (`opencode models`); model nào gọi công cụ ổn định trong worktree; giới hạn đồng thời và giá của Ollama Cloud (các trang không thống nhất, có thay đổi ngày 31/08/2026).
10. Model Google (mục 2.2): script gọi API tạo ảnh/video chưa viết, chưa thử một lượt tạo thật; giá mỗi lượt; `agy` ở chế độ tương tác trong herdr-core có báo trạng thái (OSC 7501) không; Space image-to-3D nào trên Hugging Face cho kết quả dùng được.
7. GitNexus: chỉ mục có đồng bộ đúng giữa nhiều worktree không (trang chính không nói rõ về worktree); `analyze` ghi đè hay hợp nhất `AGENTS.md`/`CLAUDE.md` ra sao (cần xem `git diff` sau khi chạy); OpenCode không có hook nên phải làm mới chỉ mục thủ công.
8. Các ngưỡng ở mục 3.4 (ví dụ "ngữ cảnh đầy quá nửa") và ở mục 1.1 (1 đến 3 skill, thợ tối đa 2) là kinh nghiệm, chưa có nguồn kiểm chứng; cần hiệu chỉnh theo thực tế.
9. Thư mục agent của OpenCode: tài liệu này ghi `.opencode/agents/`, còn repo MATHY-AI đang dùng `.opencode/agent/`; cần xác nhận bản OpenCode đang cài nhận thư mục nào (hoặc cả hai).

## Nguồn tham khảo

- herdr-mesh (MCP bọc CLI herdr, đăng ký theo từng agent, đích là tên agent/mã pane, `herdr_relay`): https://github.com/runchr-works/herdr-mesh ; https://github.com/wquesadac/herdr-mesh
- herdr-mesh-safe (lease cho controller/reviewer/writer): https://glama.ai/mcp/servers/pfoe5pzsjj
- Quy trình gửi tin an toàn giữa agent trong herdr (kiểm trạng thái, chờ idle/done/blocked, `herdr agent prompt`): https://claudskills.com/skills/herdr-agent-comms/SKILL.md
- Plugin cộng đồng cho worktree + OpenCode trong herdr (herdr-symphony, worktender): https://github.com/yigitkonur/awesome-herdr/blob/main/README.md
- herdr-core (`hc`): `hc --help`, `hc <lệnh> --help`, `hc --skill` trên máy; https://github.com/herdrdev/herdr-core ; kết quả chạy thật ghi ở mục 4.2.1
- HERDR (kiến trúc TUI/core/app, attach từ xa): https://herdr.dev/app ; https://www.eesel.ai/blog/herdr ; https://notes.dsebastien.net/30+Areas/33+Permanent+notes/33.02+Content/Herdr ; https://betterstack.com/community/guides/ai/herdr-ai-agent/
- GitNexus (đồ thị tri thức mã nguồn qua MCP, mức hỗ trợ từng agent, giấy phép, hook): https://github.com/abhigyanpatwari/GitNexus ; https://unpkg.com/gitnexus@latest/README.md ; https://socket.dev/npm/package/gitnexus
- Nguồn model cho OpenCode: https://mintlify.com/ollama/ollama/integrations/opencode ; https://git.joshthomas.dev/mirrors/opencode/commit/883ed4d424082a8b132d6c7ba985161bb0d7e7a7 (thêm Ollama Cloud vào OpenCode) ; https://openrouter.ai/docs/cookbook/coding-agents/opencode-integration ; https://www.developersdigest.tech/setup/openrouter/opencode ; https://opencode.ai/v1/docs/providers.md
- Gói và giá Ollama Cloud (không thống nhất giữa các trang, cần xem lại): https://registry.ollama.ai/cloud ; https://www.spheron.network/blog/ollama-cloud-pricing/ ; https://www.lilachbullock.com/is-ollama-free/
- OpenCode (agent theo model/quyền, `.opencode/agents/`, `opencode.json`): https://opencode.ai/docs/agents/ ; https://opencode.ai/docs/config.md
- OpenCode v2 trên máy (2026-11-18): `opencode --version`, `opencode debug paths`, `opencode upgrade --help`, `npm view @opencode/cli version`
- Antigravity CLI: `agy --help`, `agy models` trên máy (agy 1.5.10, 2026-11-18)
- Model Google tạo ảnh/video qua OpenRouter: https://openrouter.ai/api/v1/models (trường `architecture.output_modalities`)
