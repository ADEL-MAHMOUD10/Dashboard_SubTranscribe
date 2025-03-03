# Stage 1: Builder
FROM python:3 AS builder

WORKDIR /app

# Create virtual environment
RUN python3 -m venv venv
ENV VIRTUAL_ENV=/app/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Stage 2: Runner
FROM python:3 AS runner

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/venv venv
ENV VIRTUAL_ENV=/app/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy application code
COPY app.py .
COPY . .

# Set environment variables
ENV FLASK_APP=app.py

# Expose port 443
EXPOSE 443

# Run Gunicorn
CMD ["gunicorn", "--bind", ":443", "--workers", "4", "--threads", "4", "app:app"]
