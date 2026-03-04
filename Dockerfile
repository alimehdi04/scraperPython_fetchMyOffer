# Use the official Microsoft Playwright image (has all OS dependencies pre-installed!)
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install the Chromium browser binaries
RUN playwright install chromium

# Copy the rest of your application code into the container
COPY . .

# Start the FastAPI server using Uvicorn
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]