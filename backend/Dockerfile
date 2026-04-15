FROM python:3.12-slim

WORKDIR /app

# Install Python deps first — cached layer, only rebuilds when requirements change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY profiles/ ./profiles/
COPY agents/ ./agents/

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
