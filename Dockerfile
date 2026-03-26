FROM python:3.11-slim

# Copy and install requirements
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy sre-bench code to /app
COPY sre-bench /app

# Set working directory
WORKDIR /app

# Expose port
EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Run the FastAPI server
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "7860"]
