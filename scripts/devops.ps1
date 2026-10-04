<#
.SYNOPSIS
    CarbonX DevOps Orchestration Script for Windows PowerShell.
.DESCRIPTION
    Provides automated lifecycle management for CarbonX containers:
    build, up, down, dev, logs, ps, test, clean.
.EXAMPLE
    .\scripts\devops.ps1 build
    .\scripts\devops.ps1 up
    .\scripts\devops.ps1 dev
    .\scripts\devops.ps1 down
#>

[CmdletBinding()]
param (
    [Parameter(Position = 0, Mandatory = $false)]
    [ValidateSet("build", "up", "down", "dev", "down-dev", "logs", "ps", "test", "clean", "help")]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"

function Show-Help {
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "  CarbonX Container & DevOps Orchestration CLI   " -ForegroundColor Cyan
    Write-Host "=================================================" -ForegroundColor Green
    Write-Host "Usage: .\scripts\devops.ps1 <command>`n"
    Write-Host "Commands:"
    Write-Host "  build     Build all production Docker images" -ForegroundColor Yellow
    Write-Host "  up        Start all production containers in background" -ForegroundColor Yellow
    Write-Host "  down      Stop and remove production containers" -ForegroundColor Yellow
    Write-Host "  dev       Start development stack with hot-reloading" -ForegroundColor Yellow
    Write-Host "  down-dev  Stop development stack" -ForegroundColor Yellow
    Write-Host "  logs      Stream live logs across all containers" -ForegroundColor Yellow
    Write-Host "  ps        Show running status of containers" -ForegroundColor Yellow
    Write-Host "  test      Run all test suites inside containers" -ForegroundColor Yellow
    Write-Host "  clean     Remove unused CarbonX images and volumes" -ForegroundColor Yellow
    Write-Host "  help      Show this help documentation" -ForegroundColor Yellow
    Write-Host ""
}

switch ($Command) {
    "build" {
        Write-Host "==> Building CarbonX production images..." -ForegroundColor Cyan
        docker compose build
    }
    "up" {
        Write-Host "==> Starting CarbonX production stack..." -ForegroundColor Cyan
        docker compose up -d
        Write-Host "`nCarbonX is running!" -ForegroundColor Green
        Write-Host "  Frontend: http://localhost:5000"
        Write-Host "  Backend Python: http://localhost:8000"
        Write-Host "  Backend Blockchain: http://localhost:3001"
        Write-Host "  Redis: localhost:6379"
    }
    "down" {
        Write-Host "==> Stopping CarbonX production stack..." -ForegroundColor Yellow
        docker compose down
    }
    "dev" {
        Write-Host "==> Starting CarbonX development stack with hot reload..." -ForegroundColor Cyan
        docker compose -f docker-compose.dev.yml up -d
        Write-Host "`nCarbonX Development stack running!" -ForegroundColor Green
        Write-Host "  Vite Dev Server: http://localhost:5000"
        Write-Host "  FastAPI Auto-reload: http://localhost:8000"
        Write-Host "  Blockchain Service: http://localhost:3001"
    }
    "down-dev" {
        Write-Host "==> Stopping CarbonX development stack..." -ForegroundColor Yellow
        docker compose -f docker-compose.dev.yml down
    }
    "logs" {
        docker compose logs -f
    }
    "ps" {
        docker compose ps
    }
    "test" {
        Write-Host "==> Running backend test suite in Docker container..." -ForegroundColor Cyan
        docker compose run --rm backend-py python -m unittest discover tests
    }
    "clean" {
        Write-Host "==> Cleaning up CarbonX containers, networks, and orphaned volumes..." -ForegroundColor Red
        docker compose down -v --remove-orphans
        docker compose -f docker-compose.dev.yml down -v --remove-orphans
    }
    default {
        Show-Help
    }
}
