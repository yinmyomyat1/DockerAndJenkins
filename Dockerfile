FROM python:3.11-slim

# 1. Set environment variables to prevent Python from buffering logs
# This ensures you see your app logs in real-time in GitHub Actions
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 2. Copy only requirements first (Optimization)
# This uses Docker's layer caching so 'pip install' doesn't run 
# every time you change a line of code—only when requirements.txt changes.
COPY requirements.txt .
# Install all Python dependencies from requirements.txt, and don’t keep any extra files to save space.
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy the rest of the application
COPY . .

# 4. Use the correct script name from your repo
CMD ["python", "imdb_etl_mysql_admin_secure.py"]
