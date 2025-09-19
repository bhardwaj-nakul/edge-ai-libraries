#!/bin/bash
# Development helper script for Traffic Intelligence Service using UV

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Traffic Intelligence Service - UV Development Script${NC}"
echo "=================================================="

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: uv is not installed${NC}"
    echo "Install uv with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo -e "${GREEN}✓ uv is installed${NC}"

# Function to show help
show_help() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  setup     - Create virtual environment and install dependencies"
    echo "  run       - Run the traffic intelligence service (backend only)"
    echo "  dev       - Run with development settings (debug mode, backend only)"
    echo "  ui        - Run the UI dashboard only"
    echo "  full      - Run both backend and UI services together"
    echo "  full-dev  - Run both services in development mode"
    echo "  test      - Run tests"
    echo "  lint      - Run linting and formatting"
    echo "  clean     - Clean up virtual environment"
    echo "  docker    - Build and run with Docker"
    echo "  help      - Show this help message"
}

# Setup virtual environment and dependencies
setup() {
    echo -e "${YELLOW}Setting up development environment...${NC}"
    
    # Create virtual environment
    uv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
    
    # Install dependencies for backend
    uv pip install -r requirements.txt
    echo -e "${GREEN}✓ Backend dependencies installed${NC}"
    
    # Install UI dependencies
    uv pip install -r ui/requirements.txt
    echo -e "${GREEN}✓ UI dependencies installed${NC}"
    
    # Install development dependencies
    uv pip install pytest pytest-asyncio httpx black flake8 mypy
    echo -e "${GREEN}✓ Development dependencies installed${NC}"
    
    echo -e "${GREEN}Setup complete! Use 'source .venv/bin/activate' to activate the environment${NC}"
}

# Run the service
run_service() {
    echo -e "${YELLOW}Starting Traffic Intelligence Service...${NC}"
    
    # Set default environment variables
    export TRAFFIC_INTELLIGENCE_PORT=${TRAFFIC_INTELLIGENCE_PORT:-8081}
    export TRAFFIC_INTELLIGENCE_HOST=${TRAFFIC_INTELLIGENCE_HOST:-0.0.0.0}
    export LOG_LEVEL=${LOG_LEVEL:-INFO}
    export INTERSECTION_ID=${INTERSECTION_ID:-"97781c36-b53a-4749-87e6-8815da99bac7"}
    export INTERSECTION_NAME=${INTERSECTION_NAME:-"Intersection-Demo"}
    
    # Development MQTT settings (disable TLS for local development)
    export MQTT_USE_TLS=${MQTT_USE_TLS:-true}
    export MQTT_HOST=${MQTT_HOST:-localhost}
    export MQTT_PORT=${MQTT_PORT:-1883}
    
    # Warn if trying to use TLS with standard MQTT port
    if [ "$MQTT_USE_TLS" = "true" ] && [ "$MQTT_PORT" = "1883" ]; then
        echo -e "${YELLOW}Warning: TLS enabled but using standard MQTT port 1883. Consider using port 8883 for TLS.${NC}"
    fi
    
    echo "Configuration:"
    echo "  Port: $TRAFFIC_INTELLIGENCE_PORT"
    echo "  Host: $TRAFFIC_INTELLIGENCE_HOST"
    echo "  Log Level: $LOG_LEVEL"
    echo "  Intersection: $INTERSECTION_NAME"
    echo "  MQTT Host: $MQTT_HOST"
    echo "  MQTT TLS: $MQTT_USE_TLS"
    echo ""
    
    # Use the launcher script that handles module paths
    uv run python run.py
}

# Run in development mode
run_dev() {
    echo -e "${YELLOW}Starting in development mode...${NC}"
    export LOG_LEVEL=DEBUG
    export TRAFFIC_INTELLIGENCE_PORT=8081
    run_service
}

# Run UI only
run_ui() {
    echo -e "${YELLOW}Starting UI Dashboard only...${NC}"
    
    # Set UI environment variables
    export APP_PORT=${APP_PORT:-7860}
    export APP_HOST=${APP_HOST:-0.0.0.0}
    export USE_API=${USE_API:-true}
    export API_URL=${API_URL:-"http://localhost:8081/api/v1/traffic/current"}
    export REFRESH_INTERVAL=${REFRESH_INTERVAL:-15}
    
    echo "UI Configuration:"
    echo "  Port: $APP_PORT"
    echo "  Host: $APP_HOST"
    echo "  API URL: $API_URL"
    echo "  Use API: $USE_API"
    echo "  Refresh Interval: $REFRESH_INTERVAL seconds"
    echo ""
    
    # Navigate to UI directory and run
    cd ui && uv run python app.py
}

# Run both backend and UI services
run_full() {
    echo -e "${YELLOW}Starting both Backend and UI services...${NC}"
    
    # Set default environment variables for both services
    export TRAFFIC_INTELLIGENCE_PORT=${TRAFFIC_INTELLIGENCE_PORT:-8081}
    export TRAFFIC_INTELLIGENCE_HOST=${TRAFFIC_INTELLIGENCE_HOST:-0.0.0.0}
    export LOG_LEVEL=${LOG_LEVEL:-INFO}
    export INTERSECTION_ID=${INTERSECTION_ID:-"97781c36-b53a-4749-87e6-8815da99bac7"}
    export INTERSECTION_NAME=${INTERSECTION_NAME:-"Intersection-Demo"}
    
    # MQTT settings
    export MQTT_USE_TLS=${MQTT_USE_TLS:-true}
    export MQTT_HOST=${MQTT_HOST:-localhost}
    export MQTT_PORT=${MQTT_PORT:-1883}
    
    # UI settings
    export APP_PORT=${APP_PORT:-7860}
    export APP_HOST=${APP_HOST:-0.0.0.0}
    export USE_API=${USE_API:-true}
    export API_URL=${API_URL:-"http://localhost:$TRAFFIC_INTELLIGENCE_PORT/api/v1/traffic/current"}
    export REFRESH_INTERVAL=${REFRESH_INTERVAL:-15}
    
    echo "Full System Configuration:"
    echo "  Backend Port: $TRAFFIC_INTELLIGENCE_PORT"
    echo "  UI Port: $APP_PORT"
    echo "  Host: $TRAFFIC_INTELLIGENCE_HOST"
    echo "  Log Level: $LOG_LEVEL"
    echo "  Intersection: $INTERSECTION_NAME"
    echo "  MQTT Host: $MQTT_HOST"
    echo "  MQTT TLS: $MQTT_USE_TLS"
    echo "  API URL: $API_URL"
    echo ""
    
    # Function to cleanup background processes
    cleanup() {
        echo -e "${YELLOW}Shutting down services...${NC}"
        kill $BACKEND_PID 2>/dev/null || true
        kill $UI_PID 2>/dev/null || true
        exit 0
    }
    
    # Set up signal handling
    trap cleanup INT TERM
    
    echo -e "${GREEN}Starting backend service...${NC}"
    # Start backend in background
    uv run python run.py &
    BACKEND_PID=$!
    
    # Wait a moment for backend to start
    sleep 3
    
    echo -e "${GREEN}Starting UI dashboard...${NC}"
    # Start UI in background
    cd ui && uv run python app.py &
    UI_PID=$!
    cd ..
    
    echo -e "${GREEN}Both services started!${NC}"
    echo "Backend API: http://$TRAFFIC_INTELLIGENCE_HOST:$TRAFFIC_INTELLIGENCE_PORT"
    echo "UI Dashboard: http://$APP_HOST:$APP_PORT"
    echo ""
    echo "Press Ctrl+C to stop both services"
    
    # Wait for either process to exit
    wait $BACKEND_PID $UI_PID
}

# Run both services in development mode
run_full_dev() {
    echo -e "${YELLOW}Starting both services in development mode...${NC}"
    export LOG_LEVEL=DEBUG
    export TRAFFIC_INTELLIGENCE_PORT=8081
    export APP_PORT=7860
    run_full
}

# Run tests
run_tests() {
    echo -e "${YELLOW}Running tests...${NC}"
    uv run pytest -v
}

# Run linting and formatting
run_lint() {
    echo -e "${YELLOW}Running linting and formatting...${NC}"
    uv run black .
    uv run flake8 .
    uv run mypy . --ignore-missing-imports
}

# Clean up
clean() {
    echo -e "${YELLOW}Cleaning up...${NC}"
    rm -rf .venv
    rm -rf __pycache__
    rm -rf .pytest_cache
    rm -rf *.egg-info
    echo -e "${GREEN}✓ Cleanup complete${NC}"
}

# Docker build and run
run_docker() {
    echo -e "${YELLOW}Building and running with Docker...${NC}"
    docker-compose up --build
}

# Main command handling
case "${1:-help}" in
    setup)
        setup
        ;;
    run)
        run_service
        ;;
    dev)
        run_dev
        ;;
    ui)
        run_ui
        ;;
    full)
        run_full
        ;;
    full-dev)
        run_full_dev
        ;;
    test)
        run_tests
        ;;
    lint)
        run_lint
        ;;
    clean)
        clean
        ;;
    docker)
        run_docker
        ;;
    help)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac