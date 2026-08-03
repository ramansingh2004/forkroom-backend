$ErrorActionPreference = "Stop"
if (-not (Get-Command kind -ErrorAction SilentlyContinue)) {
    throw "Missing required command: kind"
}

kind delete cluster --name forkroom
