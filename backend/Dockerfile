# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    QWEN_DOMAIN_CONCURRENCY=6

WORKDIR /app

RUN set -eux; \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    if [ -f /etc/apt/sources.list ]; then sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list; fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
        -r requirements.txt

COPY app ./app
COPY template_rules.json ./
COPY domain-contracts ./domain-contracts
COPY prompt-templates ./prompt-templates
COPY test-fixtures/*.docx ./test-fixtures/
RUN mkdir -p /app/data/artifacts /app/data/logs \
    && test -f /app/template_rules.json \
    && test -f /app/prompt-templates/domain-extraction.txt \
    && test -f /app/domain-contracts/header_procedure.json \
    && test -f /app/prompt-templates/domains/online-money.txt \
    && test -f /app/app/data/__init__.py \
    && test -f /app/app/data/rules.py \
    && test -f /app/test-fixtures/01-baseline.docx \
    && test -f /app/test-fixtures/06-all-statuses-demo.docx \
    && python -c "from app.data.rules import TEMPLATE_RULES; from app.data.domain_contracts import DOMAIN_CONTRACTS"

EXPOSE 8787
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
