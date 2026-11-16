FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy package metadata required by Poetry install
COPY pyproject.toml poetry.lock* README.md ./

# Install dependencies
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

# Copy app
COPY app ./app
COPY scripts ./scripts
# Migrations ship in the image so the production stack can run them without a source mount.
COPY alembic ./alembic
COPY alembic.ini ./

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
