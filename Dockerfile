FROM python:3.14-slim
LABEL maintainer="Thomas Ingvarsson <ingvarsson.thomas@gmail.com>"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ongabot /ongabot
COPY CHANGELOG.md /ongabot/CHANGELOG.md

ENV API_TOKEN=''

WORKDIR /ongabot

CMD ["./ongabot.py"]
