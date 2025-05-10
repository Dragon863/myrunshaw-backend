FROM python:3.13-slim

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY . /app

CMD ["fastapi", "run", "app/app.py", "--proxy-headers", "--port", "5006", "--workers", "1"]