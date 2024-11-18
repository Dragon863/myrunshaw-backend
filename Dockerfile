FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5005

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5005", "app:app"]
