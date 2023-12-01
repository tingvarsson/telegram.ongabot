FROM python:3.12-alpine3.17
LABEL maintainer Thomas Ingvarsson <ingvarsson.thomas@gmail.com>

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY ongabot /ongabot

ENV API_TOKEN=''

WORKDIR /ongabot

CMD ["./ongabot.py"]
