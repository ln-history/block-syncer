FROM python:3.13-alpine

# Install system deps
RUN apk update && apk add --no-cache \
    curl \
    ca-certificates \
    gcc \
    libressl-dev \
    musl-dev \
    py3-pip \
    python3-dev \
    libevent-dev

WORKDIR /app

COPY certs/ ./certs/
COPY requirements.txt ./
COPY main.py ./
COPY .env ./

RUN pip install --no-cache-dir -r requirements.txt

VOLUME ["/app/data"]

CMD ["python", "main.py", "--interval", "60"]
