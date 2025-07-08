FROM python:3.13-alpine3.22
LABEL maintainer Thomas Ingvarsson <ingvarsson.thomas@gmail.com>

RUN apk update && apk add bind-tools

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY ongabot /ongabot

ENV API_TOKEN=''

WORKDIR /ongabot

CMD ["./ongabot.py"]
