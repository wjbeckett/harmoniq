# Use an official Python runtime as a parent image
FROM python:3.10-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    # Set Python path (optional, helps with imports sometimes)
    PYTHONPATH=/app

# Create app directory
WORKDIR /app

# Install system dependencies (added curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./harmoniq /app/harmoniq

# --- Create config directory ---
RUN mkdir -p /app/config

COPY ./config.yaml.example /app/config/config.yaml

# Create logs directory for web UI
RUN mkdir -p /app/logs

# Expose web UI port
EXPOSE 7845

# Create startup script that runs both scheduler and web server
RUN echo '#!/bin/bash\n\
echo "🎵 Starting Harmoniq..."\n\
echo "📊 Web Dashboard: http://localhost:7845"\n\
echo "📚 API Docs: http://localhost:7845/api/docs"\n\
echo ""\n\
# Start scheduler in background\n\
python -m harmoniq.scheduler_main &\n\
SCHEDULER_PID=$!\n\
# Start web server in background\n\
python -m harmoniq.web.web_main &\n\
WEB_PID=$!\n\
echo "✅ Harmoniq started successfully!"\n\
echo "🔄 Scheduler PID: $SCHEDULER_PID"\n\
echo "🌐 Web Server PID: $WEB_PID"\n\
echo ""\n\
# Function to handle shutdown\n\
shutdown() {\n\
    echo "🛑 Shutting down Harmoniq..."\n\
    kill $SCHEDULER_PID $WEB_PID 2>/dev/null\n\
    wait $SCHEDULER_PID $WEB_PID 2>/dev/null\n\
    echo "✅ Shutdown complete"\n\
    exit 0\n\
}\n\
# Trap signals\n\
trap shutdown SIGTERM SIGINT\n\
# Wait for processes\n\
wait' > /app/start.sh

RUN chmod +x /app/start.sh

# Health check for web UI
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:7845/api/health || exit 1

# Set the command to run both applications
CMD ["/app/start.sh"]
