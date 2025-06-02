# Use an official Python runtime as a parent image
FROM python:3.10-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    # Set timezone if needed by system libraries (might not be strictly necessary if using pytz later)
    # TZ=UTC
    # Set Python path (optional, helps with imports sometimes)
    PYTHONPATH=/app

# Create app directory
WORKDIR /app

# Install system dependencies if needed (e.g., for timezone data, though handled by Python usually)
# RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./harmoniq /app/harmoniq

# --- Create config directory ---
RUN mkdir -p /app/config

COPY ./config.yaml.example /app/config/config.yaml

# Set the command to run the application
CMD ["python", "-m", "harmoniq.scheduler_main"]