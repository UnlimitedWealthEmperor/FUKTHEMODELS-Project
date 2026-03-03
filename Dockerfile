FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Railway provides PORT env variable
ENV PORT=8000

# Run the app - use shell form to expand $PORT
CMD python -m uvicorn main:app --host 0.0.0.0 --port $PORT
