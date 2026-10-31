FROM python:3.10-slim
RUN apt-get update && apt-get install -y ffmpeg git
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
CMD uvicorn main:app --host 0.0.0.0 --port 10000
