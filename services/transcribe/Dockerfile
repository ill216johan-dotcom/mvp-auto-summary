FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY transcribe_server.py .
COPY requirements.txt .
RUN pip install -r requirements.txt
EXPOSE 9001
HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:9001/health || exit 1
CMD ["python3", "transcribe_server.py"]
