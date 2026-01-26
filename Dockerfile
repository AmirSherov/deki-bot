FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY r.txt /app/r.txt
RUN pip install --no-cache-dir -r /app/r.txt

COPY .env /app/.env
COPY app /app/app

CMD ["python", "-m", "app.main"]
