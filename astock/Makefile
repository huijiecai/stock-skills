# astock/Makefile
BINARY=astock
GOBUILD=go build
GOCLEAN=go clean
BINARY_DIR=./build

.PHONY: all build clean test run

all: build

build:
	$(GOBUILD) -o $(BINARY_DIR)/$(BINARY) ./cmd/astock/

clean:
	$(GOCLEAN)
	rm -rf $(BINARY_DIR)

test:
	go test ./internal/... ./cmd/... -v

run:
	go run ./cmd/astock/ --help

install:
	$(GOBUILD) -o $(GOPATH)/bin/$(BINARY) ./cmd/astock/

lint:
	go vet ./...
