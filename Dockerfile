FROM python:3.11-alpine3.17
LABEL maintainer Thomas Ingvarsson <ingvarsson.thomas@gmail.com>

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY togabot /togabot

ENV API_TOKEN=''

WORKDIR /togabot

CMD ["./togabot.py"]
