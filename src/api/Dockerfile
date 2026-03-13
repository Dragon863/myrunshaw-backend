FROM python:3.13-slim

WORKDIR /app

ENV POETRY_VERSION=2.3.2 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

COPY ./pyproject.toml ./poetry.lock /app/

RUN poetry install --no-root --only main

COPY . /app

CMD ["fastapi", "run", "app/app.py", "--proxy-headers", "--port", "5006", "--workers", "3"]