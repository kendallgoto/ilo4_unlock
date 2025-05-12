FROM debian:bullseye-slim

RUN apt-get update && \ 
    apt-get install -y python2-minimal git curl wget && \
    rm -rf /var/lib/apt/lists/*

RUN curl https://bootstrap.pypa.io/pip/2.7/get-pip.py --output get-pip.py && \
    python2 get-pip.py && \
    rm get-pip.py

RUN python2 -m pip install virtualenv

WORKDIR /app

COPY ./requirements.txt /app

RUN mkdir /home/python && \
    python2 -m virtualenv /home/python/venv 

RUN /bin/bash -c "source /home/python/venv/bin/activate && pip install -r /app/requirements.txt"

RUN git config --global --add safe.directory /app

ENTRYPOINT [ "/app/docker_entrypoint.sh" ]
