$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$requiredCommands = @("docker", "kind", "kubectl", "helm")
foreach ($command in $requiredCommands) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $command"
    }
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repositoryRoot

if (-not (kind get clusters | Select-String -SimpleMatch "forkroom")) {
    kind create cluster --config k8s/kind-config.yaml
}

docker build -t forkroom-api:dev .
docker build -t forkroom-collaboration:dev collaboration

kind load docker-image forkroom-api:dev --name forkroom
kind load docker-image forkroom-collaboration:dev --name forkroom

helm upgrade --install forkroom helm/forkroom `
    --namespace forkroom `
    --create-namespace `
    --values helm/forkroom/values-kind.yaml `
    --wait `
    --timeout 10m

kubectl get pods --namespace forkroom
Write-Host "ForkRoom API: http://localhost:8081"
Write-Host "Collaboration WebSocket: ws://localhost:1235"
