# ================================================================
# Stage 1: Builder
# ================================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy

ARG TARGETARCH

# --- Cài build-time system dependencies ---
# gcc/g++     : compile C extensions (scipy, pyodbc)
# unixodbc-dev: header files để compile pyodbc
# libpq-dev   : PostgreSQL client headers (nếu dùng pyodbc với PostgreSQL)
# curl        : dùng để kiểm tra health trong debug nếu cần
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    unixodbc-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# --- Copy shared libraries cần thiết cho runtime distroless ---
# pyodbc cần libodbc.so.2 (unixODBC runtime) — không có sẵn trong distroless
# libgcc_s, libm, libz, libc là nền tảng cho Python và NumPy/SciPy
# TARGETARCH là built-in arg của docker buildx (amd64 | arm64)
RUN if [ "$TARGETARCH" = "amd64" ]; then LIBARCH="x86_64"; \
    elif [ "$TARGETARCH" = "arm64" ]; then LIBARCH="aarch64"; \
    else LIBARCH="unknown"; fi \
    && mkdir -p /lib/multi-arch \
    && cp /lib/${LIBARCH}-linux-gnu/libc.so.6      /lib/multi-arch/ \
    && cp /lib/${LIBARCH}-linux-gnu/libm.so.6      /lib/multi-arch/ \
    && cp /lib/${LIBARCH}-linux-gnu/libz.so.1      /lib/multi-arch/ \
    && cp /lib/${LIBARCH}-linux-gnu/libgcc_s.so.1  /lib/multi-arch/ \
    # libodbc: runtime của unixODBC . bắt buộc cho pyodbc
    && cp /usr/lib/${LIBARCH}-linux-gnu/libodbc.so.2  /lib/multi-arch/ \
    # libodbcinst: quản lý ODBC driver configuration
    && cp /usr/lib/${LIBARCH}-linux-gnu/libodbcinst.so.2 /lib/multi-arch/ \
    # libgomp: OpenMP runtime — cần cho NumPy/SciPy parallel operations
    && cp /usr/lib/${LIBARCH}-linux-gnu/libgomp.so.1  /lib/multi-arch/ \
    # libstdc++: C++ standard library — cần cho SciPy, Matplotlib
    && cp /usr/lib/${LIBARCH}-linux-gnu/libstdc++.so.6 /lib/multi-arch/

WORKDIR /build

# --- Cài Python dependencies với layer cache tối ưu ---
# mount type=cache : tái sử dụng pip/uv cache giữa các lần build
# mount type=bind  : bind pyproject.toml và uv.lock mà không COPY vào image
# --frozen         : chỉ cài đúng version trong uv.lock, không update
# --no-install-project: không cài project hiện tại vào .venv (chỉ deps)
# --no-dev         : bỏ qua dev dependencies
# --no-editable    : cài dưới dạng wheel thay vì editable link
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --no-editable

# ================================================================
# Stage 2: Runtime (production image)
# distroless/base-debian12:nonroot
#   - Không có shell, không có package manager → attack surface tối thiểu
#   - nonroot: chạy với UID=65532 mặc định
#   - base-debian12 đã có sẵn: libssl, libcrypt, ld-linux, ...
# ================================================================
# ... (phần builder giữ nguyên) ...

FROM gcr.io/distroless/base-debian12:nonroot AS runtime

WORKDIR /app

COPY --from=builder /lib/multi-arch/                        /lib/multi-arch/
COPY --from=builder /usr/local/lib/libpython3.12.so.1.0     /usr/local/lib/
COPY --from=builder /usr/local/bin/python /usr/local/bin/python-base
COPY --from=builder /usr/local/bin/python                   /usr/local/bin/python
COPY --from=builder --chown=nonroot:nonroot /build/.venv/   /app/.venv/

# Chỉ copy thư viện — không cần bất kỳ file nào từ ngoài
COPY --chown=nonroot:nonroot spyswat/ ./swat_toolkit/

ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    LD_LIBRARY_PATH=/lib/multi-arch \
    VIRTUAL_ENV=/app/.venv

# Chạy như module — hoàn toàn tự chứa
ENTRYPOINT ["/app/.venv/bin/python", "-m", "swat_toolkit"]