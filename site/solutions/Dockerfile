FROM python:3.15-slim

WORKDIR /app
COPY . /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MADMALLARD_DATA_DIR=/data

RUN mkdir -p /data

EXPOSE 8000
CMD ["python", "server.py"]
