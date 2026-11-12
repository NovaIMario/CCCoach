FROM python:3.12-slim

# g++ for the C++ code runner
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Run as an unprivileged user, so code submitted to the runner can't touch the app's files.
RUN useradd --create-home coach && mkdir -p data && chown -R coach data
USER coach

ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
