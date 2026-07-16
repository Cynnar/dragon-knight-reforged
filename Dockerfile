# Dragon Knight — application image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps: build toolchain + MariaDB/MySQL client headers for mysqlclient.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user with a fixed uid/gid so bind-mounted host dirs
# (staticfiles, media under /docker/data) have predictable ownership.
RUN groupadd -g 1000 appuser \
    && useradd -u 1000 -g 1000 --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
