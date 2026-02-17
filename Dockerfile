FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install dependencies (no dev extras)
RUN uv sync --no-dev --frozen

# Create data directory
RUN mkdir -p /app/data /app/config

# Default command (overridden by docker-compose)
CMD ["uv", "run", "python", "-m", "financial_advisor.main"]
