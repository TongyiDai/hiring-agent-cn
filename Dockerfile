FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY hiring_agent_cn ./hiring_agent_cn
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 reviewer
USER reviewer
EXPOSE 8000
CMD ["hiring-agent-cn", "serve", "--host", "0.0.0.0", "--port", "8000"]
