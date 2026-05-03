# syntax=docker/dockerfile:1.7

FROM golang:1.22-alpine AS builder

WORKDIR /src

COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

COPY . .

RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux \
    go build -trimpath -ldflags="-s -w" -o /out/api ./cmd

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata \
 && addgroup -S app \
 && adduser  -S app -G app

WORKDIR /app
COPY --from=builder /out/api /app/api

USER app
EXPOSE 8080

ENTRYPOINT ["/app/api"]
