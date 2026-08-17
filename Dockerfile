FROM eu.gcr.io/ramadhan-s4g/eo-base:latest

WORKDIR /usr/src/app

COPY private_key.json .

RUN gcloud auth activate-service-account --key-file private_key.json

COPY job/requirements.txt .

RUN python3 -m venv .venv && \
  .venv/bin/pip install -r requirements.txt

COPY __init__.py .

ENV GS_NO_SIGN_REQUEST=YES
