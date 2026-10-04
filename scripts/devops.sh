#!/usr/bin/env bash
# ==============================================================================
# CarbonX DevOps Orchestration Script for Linux and macOS
# ==============================================================================
set -e

COMMAND="${1:-help}"

show_help() {
  echo -e "\033[1;32m=================================================\033[0m"
  echo -e "\033[1;36m  CarbonX Container & DevOps Orchestration CLI   \033[0m"
  echo -e "\033[1;32m=================================================\033[0m"
  echo -e "Usage: ./scripts/devops.sh <command>\n"
  echo -e "Commands:"
  echo -e "  \033[1;33mbuild\033[0m     Build all production Docker images"
  echo -e "  \033[1;33mup\033[0m        Start all production containers in background"
  echo -e "  \033[1;33mdown\033[0m      Stop and remove production containers"
  echo -e "  \033[1;33mdev\033[0m       Start development stack with hot-reloading"
  echo -e "  \033[1;33mdown-dev\033[0m  Stop development stack"
  echo -e "  \033[1;33mlogs\033[0m      Stream live logs across all containers"
  echo -e "  \033[1;33mps\033[0m        Show running status of containers"
  echo -e "  \033[1;33mtest\033[0m      Run all test suites inside containers"
  echo -e "  \033[1;33mclean\033[0m     Remove unused CarbonX images and volumes"
  echo -e "  \033[1;33mhelp\033[0m      Show this help documentation"
  echo ""
}

case "$COMMAND" in
  build)
    echo -e "\033[1;36m==> Building CarbonX production images...\033[0m"
    docker compose build
    ;;
  up)
    echo -e "\033[1;36m==> Starting CarbonX production stack...\033[0m"
    docker compose up -d
    echo -e "\n\033[1;32mCarbonX is running!\033[0m"
    echo "  Frontend: http://localhost:5000"
    echo "  Backend Python: http://localhost:8000"
    echo "  Backend Blockchain: http://localhost:3001"
    echo "  Redis: localhost:6379"
    ;;
  down)
    echo -e "\033[1;33m==> Stopping CarbonX production stack...\033[0m"
    docker compose down
    ;;
  dev)
    echo -e "\033[1;36m==> Starting CarbonX development stack with hot reload...\033[0m"
    docker compose -f docker-compose.dev.yml up -d
    echo -e "\n\033[1;32mCarbonX Development stack running!\033[0m"
    echo "  Vite Dev Server: http://localhost:5000"
    echo "  FastAPI Auto-reload: http://localhost:8000"
    echo "  Blockchain Service: http://localhost:3001"
    ;;
  down-dev)
    echo -e "\033[1;33m==> Stopping CarbonX development stack...\033[0m"
    docker compose -f docker-compose.dev.yml down
    ;;
  logs)
    docker compose logs -f
    ;;
  ps)
    docker compose ps
    ;;
  test)
    echo -e "\033[1;36m==> Running backend test suite in Docker container...\033[0m"
    docker compose run --rm backend-py python -m unittest discover tests
    ;;
  clean)
    echo -e "\033[1;31m==> Cleaning up CarbonX containers, networks, and orphaned volumes...\033[0m"
    docker compose down -v --remove-orphans
    docker compose -f docker-compose.dev.yml down -v --remove-orphans
    ;;
  *)
    show_help
    ;;
esac
