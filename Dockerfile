FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY app/ app/
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "gunicorn 'app:create_app()' --bind 0.0.0.0:$PORT"]
