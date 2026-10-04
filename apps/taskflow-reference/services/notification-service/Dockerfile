FROM golang:1.22-alpine AS builder

WORKDIR /build

COPY go.mod ./
RUN go mod download 2>/dev/null || true

COPY main.go ./
RUN go mod tidy && go build -o notification-service main.go

FROM alpine:3.20

WORKDIR /app
COPY --from=builder /build/notification-service .

EXPOSE 8003

CMD ["./notification-service"]
