FROM debian:bullseye-slim AS builder

RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv curl wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN python3 -m venv venv
RUN /bin/bash -c "source venv/bin/activate && python3 -m pip install -r requirements.txt && ./build.sh init && ./build.sh latest"

FROM scratch
COPY --from=builder /app/binaries/flash_ilo4 /app/binaries/CP027911.xml /
COPY --from=builder /app/build/ilo4_*.bin.patched /ilo4_250.bin
