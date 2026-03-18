GO ?= go
IMG ?= tenant-node-assignment-operator:latest
HELM_CHART ?= charts/tenant-node-assignment-operator

.PHONY: all build test coverage lint docker-build helm-lint helm-template run-local clean

all: build test lint

## Build
build:
	$(GO) build -o bin/manager cmd/main.go

## Test
test:
	$(GO) test ./internal/... ./api/... -v -count=1

## Coverage
coverage:
	$(GO) test ./internal/... ./api/... -v -coverprofile=coverage.out -covermode=atomic
	$(GO) tool cover -func=coverage.out
	$(GO) tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report: coverage.html"

## Lint
lint:
	$(GO) vet ./...
	@echo "Lint passed"

## Docker
docker-build:
	docker build -t $(IMG) .

## Helm
helm-lint:
	helm lint $(HELM_CHART)

helm-template:
	helm template test $(HELM_CHART) --namespace compute-platform-system

## Run locally (requires kubeconfig)
run-local:
	$(GO) run cmd/main.go --leader-elect=false

## Clean
clean:
	rm -rf bin/ coverage.out coverage.html

## Install CRD (requires kubectl)
install-crd:
	kubectl apply -f $(HELM_CHART)/templates/crd.yaml

## Uninstall CRD
uninstall-crd:
	kubectl delete -f $(HELM_CHART)/templates/crd.yaml --ignore-not-found
