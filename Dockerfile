# Use official Python image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy all files into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8000
EXPOSE 8000

# Start FastAPI using Uvicorn
CMD ["fastapi", "run", "main.py"]
