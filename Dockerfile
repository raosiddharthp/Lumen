FROM python:3.11-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
COPY agents ./agents
ENTRYPOINT ["sh", "-c", "exec python -m uvicorn \"$APP\" --host 0.0.0.0 --port \"$PORT\""]
