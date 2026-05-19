FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY config ./config
COPY prompts ./prompts
COPY src ./src

RUN pip install --upgrade pip \
    && pip install .

ENTRYPOINT ["react-agent"]
CMD ["--help"]
