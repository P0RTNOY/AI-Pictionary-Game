FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY check_keys.py .

ENV DATABASE_URL=sqlite:////data/ai_pictionary.db
ENV ENV=production DEBUG=false AUTO_CREATE_TABLES=false
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
