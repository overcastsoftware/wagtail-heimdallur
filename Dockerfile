# Development and testing environment for wagtail-heimdallur
# Provides Python 3.14, Node.js, and all test tooling

FROM python:3.14-rc-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Verify Node.js and npm installation
RUN node --version && npm --version

WORKDIR /app

# Install Python test tooling upfront (these rarely change)
RUN pip install --no-cache-dir \
    pytest \
    pytest-django \
    hypothesis \
    tox \
    pytest-httpx \
    httpx \
    Django>=4.2 \
    wagtail>=6.0

# Copy project files and install in editable mode with dev dependencies
COPY pyproject.toml ./
COPY wagtail_heimdallur/ ./wagtail_heimdallur/
COPY tests/ ./tests/

RUN pip install --no-cache-dir -e ".[dev]" || true

# Default command runs the full test suite
CMD ["pytest"]
