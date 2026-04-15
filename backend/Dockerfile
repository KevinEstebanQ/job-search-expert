# Official Playwright image includes Chromium + all system dependencies.
# Headless browser scraping works out of the box on any OS.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Install Python deps first — cached layer, only rebuilds when requirements change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-install Chromium browser (base image has system libs, this adds the browser binary)
RUN playwright install chromium

# Copy application code
COPY backend/ ./backend/
COPY profiles/ ./profiles/
COPY agents/ ./agents/

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
