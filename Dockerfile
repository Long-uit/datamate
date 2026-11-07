# ==============================================================================
# Dockerfile — DataMate Official Submission Image (Zalo AI Challenge 2026)
# Phase 4: Calibrated Abstention, Offline Isolation & Reproducibility
# ==============================================================================

FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime

LABEL maintainer="DataMate Team (Long & Phat) <ldlong02112007@gmail.com, dangminhphat753@gmail.com>"
LABEL challenge="Zalo AI Challenge 2026"
LABEL track="DataMate - Retail Data Analysis & Code Generation"

# Thiết lập biến môi trường chuẩn bị cho môi trường ngoại tuyến (100% Offline)
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    DATAMATE_OFFLINE_MODE=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Cài đặt các gói hệ thống cần thiết
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    build-essential \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc và các thư mục theo chuẩn BTC
WORKDIR /app

RUN mkdir -p /app /data /result /result/logs /app/weights

# Cài đặt các gói thư viện Python từ requirements-docker.txt
COPY requirements-docker.txt /app/
RUN pip install --no-cache-dir -r requirements-docker.txt

# Sao chép toàn bộ mã nguồn hệ thống
COPY pyproject.toml /app/
COPY config/ /app/config/
COPY src/ /app/src/
COPY predict.py /app/
COPY predict.sh /app/

# Cài đặt package datamate ở chế độ editable không phụ thuộc mạng
RUN pip install --no-cache-dir -e . --no-deps

# Cấp quyền thực thi cho kịch bản chạy chính
RUN chmod +x /app/predict.sh

# Cổng kiểm định ngoại tuyến mặc định
ENTRYPOINT ["/bin/bash", "/app/predict.sh"]
CMD ["/data", "/result/submission.jsonl", "/result/logs"]
