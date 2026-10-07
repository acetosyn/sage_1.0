FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV SAGE_ENV=production SAGE_DEBUG=false SAGE_SQLITE_FALLBACK=false
CMD ["gunicorn", "--workers", "3", "--threads", "4", "--timeout", "120", "--bind", "0.0.0.0:8000", "wsgi:app"]
