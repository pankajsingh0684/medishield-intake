FROM golang:1.24-alpine AS builder

ARG MINIO_VERSION

RUN apk add --no-cache git
RUN git clone --depth 1 --branch "${MINIO_VERSION}" https://github.com/minio/minio.git /src

WORKDIR /src
RUN CGO_ENABLED=0 go build \
    -tags kqueue \
    -trimpath \
    --ldflags "$(go run buildscripts/gen-ldflags.go)" \
    -o /out/minio

FROM alpine:3.21

RUN apk add --no-cache ca-certificates curl \
    && addgroup -S minio \
    && adduser -S -G minio minio \
    && mkdir -p /data \
    && chown minio:minio /data

COPY --from=builder /out/minio /usr/local/bin/minio

USER minio
VOLUME ["/data"]
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]