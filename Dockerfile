FROM python:3.14-slim
LABEL authors="brck"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir /data \
    && chown app /data

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py config.py ./

USER app

WORKDIR /data

CMD ["python", "/app/main.py"]