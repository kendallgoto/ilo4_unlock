FROM debian:bullseye-slim AS builder

RUN apt-get update && \ 
    apt-get install -y python2-minimal git curl wget && \
    rm -rf /var/lib/apt/lists/*

RUN curl https://bootstrap.pypa.io/pip/2.7/get-pip.py --output get-pip.py && \
    python2 get-pip.py && \
    rm get-pip.py

RUN python2 -m pip install virtualenv

WORKDIR /app
COPY . .
RUN python2 -m virtualenv venv
RUN /bin/bash -c "source venv/bin/activate && pip install -r requirements.txt"
RUN git config --global --add safe.directory /app

RUN /bin/bash -c "source venv/bin/activate && ./build.sh init && ./build.sh latest"

FROM scratch
COPY --from=builder /app/binaries/flash_ilo4 /app/binaries/CP027911.xml /
COPY --from=builder /app/build/ilo4_*.bin.patched /ilo4_250.bin
