FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY shamsbot ./shamsbot
RUN pip install --no-cache-dir .

ENV STATE_DB=/data/bot.sqlite3
VOLUME ["/data"]
CMD ["shams-bot"]

