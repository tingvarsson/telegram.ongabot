FROM python:3.15-slim
LABEL maintainer="Thomas Ingvarsson <ingvarsson.thomas@gmail.com>"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ongabot /ongabot
COPY CHANGELOG.md /ongabot/CHANGELOG.md

ENV API_TOKEN=''

WORKDIR /ongabot

# Healthy while the bot keeps refreshing its heartbeat file (see ongabot/healthcheck.py). The
# start period covers startup work; the start interval lets a fresh container turn healthy in
# seconds rather than after a full interval.
HEALTHCHECK --interval=60s --timeout=10s --start-period=2m --start-interval=10s --retries=3 \
  CMD ["python3", "healthcheck.py"]

CMD ["./ongabot.py"]
