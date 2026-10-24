FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY r.txt /app/r.txt
RUN pip install --no-cache-dir -r /app/r.txt

COPY app /app/app

EXPOSE 5555

CMD ["python", "-m", "app.main"]
