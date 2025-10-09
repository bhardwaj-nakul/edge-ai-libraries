#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Combined Scene Intelligence Setup and Orchestration Script
# This script combines setup and orchestration functionality for Scene Intelligence services

# Color codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Setting variables for directories used as volume mounts
SOURCE="src"
SECRETS_DIR="${SOURCE}/secrets"
DOCKER_DIR="docker"
COMPOSE_MAIN="${DOCKER_DIR}/compose.yaml"

# Function to show comprehensive help
show_help() {
    echo -e "${BLUE}Scene Intelligence Setup and Orchestration Script${NC}"
    echo -e "${YELLOW}USAGE: ${GREEN}source setup.sh ${BLUE}[COMMAND] [OPTIONS]${NC}"
    echo -e "-----------------------------------------------------------------"
    echo ""
    echo -e "${BLUE}Available Commands:${NC}"
    echo -e "  ${GREEN}setup${NC}         Complete setup process (secrets + videos + build + start)"
    echo -e "  ${GREEN}build${NC}         Build all Docker container images"
    echo -e "  ${GREEN}up${NC}            Start all containerized services"
    echo -e "  ${GREEN}down${NC}          Stop all running services"
    echo -e "  ${GREEN}restart${NC}       Stop and restart all services"
    echo -e "  ${GREEN}status${NC}        Display status of all services and their URLs"
    echo -e "  ${GREEN}logs${NC}          Show service logs (use with --follow to stream)"
    echo -e "  ${GREEN}secrets${NC}       Generate secrets only"
    echo -e "  ${GREEN}videos${NC}        Download demo videos only"
    echo -e "  ${GREEN}clean${NC}         Stop services and remove containers, volumes, and images"
    echo -e "  ${GREEN}help${NC}          Show this comprehensive help message"
    echo ""
    echo -e "${BLUE}Prerequisites:${NC}"
    echo -e "  • Docker and Docker Compose must be installed"
    echo -e "  • Sufficient disk space for container images and data"
    echo ""
    echo -e "${BLUE}Quick Start:${NC}"
    echo -e "  ${YELLOW}source setup.sh setup${NC}    # Run this command for first-time setup"
    echo -e "-----------------------------------------------------------------"
}

# Function to check if Docker Compose is available
check_docker_compose() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
        return 1
    fi
    
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}Error: Docker Compose is not available${NC}"
        return 1
    fi
}

# Handle help and argument validation
if [ "$#" -eq 0 ] || [ "$1" = "help" ]; then
    show_help
    if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 0; else return 0; fi
fi

# Check for too many arguments
if [ "$#" -gt 2 ]; then
    echo -e "${RED}ERROR: Too many arguments provided.${NC}"
    echo -e "${YELLOW}Use 'help' for usage information${NC}"
    if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 1; else return 1; fi
fi



# Export all environment variables
# Base configuration
export HOST_IP=$(ip route get 1 | awk '{print $7}')  # Fetch the host IP
# Add HOST_IP to no_proxy only if not already present
[[ $no_proxy != *"${HOST_IP}"* ]] && export no_proxy="${no_proxy},${HOST_IP}"
export TAG=${TAG:-latest}
export REGISTRY_URL=${REGISTRY_URL:-intel}
export PROJECT_NAME=${PROJECT_NAME:-}

# Construct registry path properly to avoid double slashes
if [[ -n "$REGISTRY_URL" && -n "$PROJECT_NAME" ]]; then
    # Both are set, combine with single slash
    export REGISTRY="${REGISTRY_URL%/}/${PROJECT_NAME%/}/"
elif [[ -n "$REGISTRY_URL" ]]; then
    # Only registry URL is set
    export REGISTRY="${REGISTRY_URL%/}/"
elif [[ -n "$PROJECT_NAME" ]]; then
    # Only project name is set
    export REGISTRY="${PROJECT_NAME%/}/"
else
    # Neither is set, use empty registry
    export REGISTRY=""
fi
echo -e "${GREEN}Using registry: ${YELLOW}$REGISTRY ${NC}"

# Scene Intelligence Service Configuration
export MQTT_PORT=${MQTT_PORT:-1883}
export SCENESCAPE_PORT=${SCENESCAPE_PORT:-443}
export SCENE_INTELLIGENCE_PORT=${SCENE_INTELLIGENCE_PORT:-8082}
export DLSTREAMER_PORT=${DLSTREAMER_PORT:-8555}

# User and group IDs
export USER_ID=$(id -u)
export USER_GROUP_ID=$(id -g)
export UID=${UID:-$(id -u)}
export GID=${GID:-$(id -g)}

# SceneScape Database Configuration
export DBROOT=${DBROOT:-/workspace}
export EXAMPLEDB=${EXAMPLEDB:-scene-intelligence.tar.bz2}

# Traffic Analysis Configuration
export TRAFFIC_BUFFER_DURATION=${TRAFFIC_BUFFER_DURATION:-60}
export LOG_LEVEL=${LOG_LEVEL:-INFO}
export DATA_RETENTION_HOURS=${DATA_RETENTION_HOURS:-24}

# SceneScape Configuration
export SCENESCAPE_URL=${SCENESCAPE_URL:-https://web.scenescape.intel.com}
export MQTT_BROKER_HOST=${MQTT_BROKER_HOST:-broker.scenescape.intel.com}
export MQTT_BROKER_PORT=${MQTT_BROKER_PORT:-1883}

# Proxy settings
export no_proxy_env=${no_proxy}

# Scene Intelligence Service Configuration
export SCENE_INTELLIGENCE_CONFIG=${SCENE_INTELLIGENCE_CONFIG:-/app/config/scene_intelligence_config.json}

# Health Check Configuration
export HEALTH_CHECK_INTERVAL=${HEALTH_CHECK_INTERVAL:-30s}
export HEALTH_CHECK_TIMEOUT=${HEALTH_CHECK_TIMEOUT:-10s}
export HEALTH_CHECK_RETRIES=${HEALTH_CHECK_RETRIES:-3}
export HEALTH_CHECK_START_PERIOD=${HEALTH_CHECK_START_PERIOD:-10s}

# VLM Service Configuration
export VLM_SERVICE_PORT=${VLM_SERVICE_PORT:-9764}
export VLM_BASE_URL=${VLM_BASE_URL:-http://vlm-openvino-serving:8000}
export VLM_MODEL=${VLM_MODEL:-Qwen/Qwen2.5-VL-3B-Instruct}
export VLM_MODEL_NAME=${VLM_MODEL_NAME:-Qwen/Qwen2.5-VL-3B-Instruct}
export HIGH_DENSITY_THRESHOLD=${HIGH_DENSITY_THRESHOLD:-5.0}
export MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS=${MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS:-2}
export VLM_COOLDOWN_MINUTES=${VLM_COOLDOWN_MINUTES:-1}
export VLM_TIMEOUT_SECONDS=${VLM_TIMEOUT_SECONDS:-300}
export VLM_MAX_COMPLETION_TOKENS=${VLM_MAX_COMPLETION_TOKENS:-500}
export VLM_TEMPERATURE=${VLM_TEMPERATURE:-0.3}
export VLM_TOP_P=${VLM_TOP_P:-0.9}
export VLM_CONFIG_FILE=${VLM_CONFIG_FILE:-config/vlm_config.json}

# AI Route Planner Configuration
export AI_ROUTE_PLANNER_PORT=${AI_ROUTE_PLANNER_PORT:-7864}
export AI_ROUTE_PLANNER_DIR=${AI_ROUTE_PLANNER_DIR:-ai-route-planner}
export SI_API_BASE=${SI_API_BASE:-http://${HOST_IP}:${SCENE_INTELLIGENCE_PORT:-8081}}

# VLM Prompts (optional environment variable overrides)
# export VLM_SYSTEM_PROMPT="Custom system prompt..."
# export VLM_TRAFFIC_ANALYSIS_PROMPT="Custom traffic analysis prompt with {intersection_id}, {directions_text}, {density_info}, {high_density_threshold} placeholders..."

# VLM OpenVINO Configuration (for VLM microservice)
export VLM_DEVICE=${VLM_DEVICE:-CPU}
export VLM_COMPRESSION_WEIGHT_FORMAT=${VLM_COMPRESSION_WEIGHT_FORMAT:-int8}
export VLM_SEED=${VLM_SEED:-42}
export VLM_WORKERS=${VLM_WORKERS:-4}  # Set to 4 for concurrent intersection analysis
export VLM_LOG_LEVEL=${VLM_LOG_LEVEL:-info}
export VLM_ACCESS_LOG_FILE=${VLM_ACCESS_LOG_FILE:-/dev/null}

# Automatically adjust VLM settings for GPU
if [[ "$VLM_DEVICE" == "GPU" ]]; then
    export VLM_COMPRESSION_WEIGHT_FORMAT=int4
    export VLM_WORKERS=1  # GPU works best with single worker
fi

# Export current user and group IDs for VLM container
export VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}' 2>/dev/null || echo "44")
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}' 2>/dev/null || echo "109")

echo -e "${GREEN}Environment variables set:${NC}"
echo -e "  HOST_IP: ${YELLOW}$HOST_IP${NC}"
echo -e "  TAG: ${YELLOW}$TAG${NC}"
echo -e "  REGISTRY: ${YELLOW}$REGISTRY${NC}"
echo -e "  MQTT_PORT: ${YELLOW}$MQTT_PORT${NC}"
echo -e "  SCENESCAPE_PORT: ${YELLOW}$SCENESCAPE_PORT${NC}"
echo -e "  SCENE_INTELLIGENCE_PORT: ${YELLOW}$SCENE_INTELLIGENCE_PORT${NC}"
echo -e "  VLM_SERVICE_PORT: ${YELLOW}$VLM_SERVICE_PORT${NC}"
echo -e "  AI_ROUTE_PLANNER_PORT: ${YELLOW}$AI_ROUTE_PLANNER_PORT${NC}"
echo -e "  SI_API_BASE: ${YELLOW}$SI_API_BASE${NC}"
echo -e "  VLM_MODEL_NAME: ${YELLOW}$VLM_MODEL_NAME${NC}"
echo -e "  VLM_WORKERS: ${YELLOW}$VLM_WORKERS${NC}"
echo -e "  VLM_DEVICE: ${YELLOW}$VLM_DEVICE${NC}"
echo -e "  HIGH_DENSITY_THRESHOLD: ${YELLOW}$HIGH_DENSITY_THRESHOLD${NC}"
echo -e "  VLM_COOLDOWN_MINUTES: ${YELLOW}$VLM_COOLDOWN_MINUTES${NC}"
echo -e "  UID: ${YELLOW}$UID${NC}"
echo -e "  GID: ${YELLOW}$GID${NC}"

# Function to generate secrets
generate_secrets() {
    echo -e "${BLUE}==> Generating secrets...${NC}"
    
    if [ ! -f "${SECRETS_DIR}/generate_secrets.sh" ]; then
        echo -e "${RED}Error: ${SECRETS_DIR}/generate_secrets.sh not found!${NC}"
        return 1
    fi
    
    # Generate secrets if they don't exist
    if [ ! -f "${SECRETS_DIR}/browser.auth" ]; then
        echo -e "${YELLOW}Generating new secrets...${NC}"
        bash "${SECRETS_DIR}/generate_secrets.sh"
        echo -e "${GREEN}Secrets generated successfully${NC}"
    else
        echo -e "${YELLOW}Secrets already exist, skipping generation${NC}"
        echo -e "${YELLOW}To force regeneration, delete ${SECRETS_DIR} and run again${NC}"
    fi
}

# Function to download demo videos
download_videos() {
    echo -e "${BLUE}==> Downloading demo videos...${NC}"
    
    VIDEO_DIR="${SOURCE}/dlstreamer-pipeline-server/videos"
    
    # Check if videos already exist
    if [ -d "${VIDEO_DIR}" ] && [ -n "$(find "${VIDEO_DIR}" -type f -name "*.ts" 2>/dev/null)" ]; then
        echo -e "${YELLOW}Videos already exist, skipping download${NC}"
        echo -e "${GREEN}Found existing videos:${NC}"
        ls -la "${VIDEO_DIR}"/*.ts 2>/dev/null | awk '{print "  " $9 " (" $5 " bytes)"}'
        return 0
    fi
    
    # Create video directory
    mkdir -p "${VIDEO_DIR}"
    
    # Video download configuration
    VIDEO_URL="https://github.com/intel/metro-ai-suite/raw/refs/heads/videos/videos"
    VIDEOS=("1122east.ts" "1122west.ts" "1122north.ts" "1122south.ts")
    
    echo -e "${YELLOW}Downloading videos from: ${VIDEO_URL}${NC}"
    
    # Download each video
    for VIDEO in "${VIDEOS[@]}"; do
        echo -e "${YELLOW}Downloading ${VIDEO}...${NC}"
        
        if curl -L --fail --progress-bar "${VIDEO_URL}/${VIDEO}" -o "${VIDEO_DIR}/${VIDEO}"; then
            echo -e "${GREEN}✓ Downloaded ${VIDEO} successfully${NC}"
        else
            echo -e "${RED}✗ Error: Failed to download ${VIDEO}${NC}"
            echo -e "${RED}Please check your internet connection and try again${NC}"
            return 1
        fi
    done
    
    echo -e "${GREEN}All videos downloaded successfully!${NC}"
    echo -e "${BLUE}Downloaded videos:${NC}"
    ls -la "${VIDEO_DIR}"/*.ts 2>/dev/null | awk '{print "  " $9 " (" $5 " bytes)"}'
}


# Function to check prerequisites (secrets and videos)
check_prerequisites() {
    echo -e "${BLUE}==> Checking prerequisites...${NC}"
    
    # Check if secrets exist
    if [ ! -f "${SECRETS_DIR}/browser.auth" ]; then
        echo -e "${YELLOW}Secrets not found. Generating them...${NC}"
        generate_secrets
        if [ $? -ne 0 ]; then
            echo -e "${RED}Failed to generate secrets${NC}"
            return 1
        fi
    else
        echo -e "${GREEN}✓ Secrets found${NC}"
    fi
    
    # Check if videos exist
    local videos_dir="${SOURCE}/dlstreamer-pipeline-server/videos"
    if [ ! -d "${videos_dir}" ] || [ -z "$(find "${videos_dir}" -name "*.ts" 2>/dev/null)" ]; then
        echo -e "${YELLOW}Demo videos not found. Downloading them...${NC}"
        download_videos
        if [ $? -ne 0 ]; then
            echo -e "${RED}Failed to download videos${NC}"
            return 1
        fi
    else
        echo -e "${GREEN}✓ Demo videos found${NC}"
    fi
    
    echo -e "${GREEN}Prerequisites check completed${NC}"
    return 0
}

# Function to show service URLs
show_service_urls() {
    echo -e "${BLUE}Service URLs:${NC}"
    echo -e "  • Scene Intelligence API: ${YELLOW}http://localhost:${SCENE_INTELLIGENCE_PORT}${NC}"
    echo -e "  • AI Route Planner: ${YELLOW}http://localhost:${AI_ROUTE_PLANNER_PORT}${NC}"
    echo -e "  • SceneScape Web: ${YELLOW}https://localhost:${SCENESCAPE_PORT}${NC}"
    echo -e "  • VLM Service: ${YELLOW}http://localhost:${VLM_SERVICE_PORT}${NC}"
    echo -e "  • MQTT Broker: ${YELLOW}localhost:${MQTT_PORT}${NC}"
    echo -e "  • DL Streamer: ${YELLOW}http://localhost:${DLSTREAMER_PORT}${NC}"
    echo ""
    echo -e "${BLUE}Scene Intelligence API Endpoints:${NC}"
    echo -e "  • Health Check: ${YELLOW}http://localhost:${SCENE_INTELLIGENCE_PORT}/health${NC}"
    echo -e "  • API Docs: ${YELLOW}http://localhost:${SCENE_INTELLIGENCE_PORT}/docs${NC}"
    echo -e "  • Traffic Summary: ${YELLOW}http://localhost:${SCENE_INTELLIGENCE_PORT}/api/v1/traffic/directional/summary${NC}"
    echo ""
    echo -e "${BLUE}Management Commands:${NC}"
    echo -e "  • View logs: ${YELLOW}source setup.sh logs --follow${NC}"
    echo -e "  • Stop services: ${YELLOW}source setup.sh down${NC}"
    echo -e "  • Check status: ${YELLOW}source setup.sh status${NC}"
}

# Function to start the service
start_service() {
    echo -e "${BLUE}==> Starting Scene Intelligence service...${NC}"
    
    # Start all services with Docker Compose
    docker compose -f $COMPOSE_MAIN up -d
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Scene Intelligence service started successfully!${NC}"
        echo ""
        show_service_urls
    else
        echo -e "${RED}Failed to start Scene Intelligence service${NC}"
        return 1
    fi
}

# Function to build Docker images
build_images() {
    echo -e "${BLUE}==> Building Docker images...${NC}"
    
    docker compose -f $COMPOSE_MAIN build
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Docker images built successfully${NC}"
    else
        echo -e "${RED}Failed to build Docker images${NC}"
        return 1
    fi
}

# Function to do full setup
full_setup() {
    echo -e "${BLUE}==> Starting full setup...${NC}"
    echo -e "${YELLOW}This will: check prerequisites, build images, and start all services${NC}"
    
    # Check prerequisites first
    check_prerequisites
    if [ $? -ne 0 ]; then
        return 1
    fi
    
    # Build all images
    build_images
    if [ $? -ne 0 ]; then
        return 1
    fi
    
    # Start all services
    start_service
    if [ $? -ne 0 ]; then
        return 1
    fi
    
    echo -e "${GREEN}==> Full setup completed successfully!${NC}"
}

# Check Docker Compose availability and load environment variables
check_docker_compose
if [ $? -ne 0 ]; then
    if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 1; else return 1; fi
fi

# Verify if required directories exist (except for environment-only commands)
if [ "$1" != "setenv" ] && [ "$1" != "down" ] && [ "$1" != "clean" ] && [ "$1" != "status" ] && [ "$1" != "logs" ]; then
    if [ ! -d "${SOURCE}" ]; then
        echo -e "${RED}Error: Source directory '${SOURCE}' not found${NC}"
        if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 1; else return 1; fi
    fi
    
    if [ ! -d "${SECRETS_DIR}" ]; then
        echo -e "${YELLOW}Warning: Secrets directory '${SECRETS_DIR}' not found${NC}"
        echo -e "${YELLOW}Secrets will be generated when needed${NC}"
    fi
fi

# Handle environment-only setup
if [ "$1" = "setenv" ]; then
    echo -e "${BLUE}Done setting up all environment variables.${NC}"
    if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 0; else return 0; fi
fi

# Main logic based on command - handles both legacy (--option) and new (option) formats
case "$1" in
    "secrets")
        generate_secrets
        ;;
    "videos")
        download_videos
        ;;
    "build")
        # Check prerequisites first
        check_prerequisites
        if [ $? -eq 0 ]; then
            build_images
        fi
        ;;
    "up")
        # Check prerequisites first
        check_prerequisites
        if [ $? -eq 0 ]; then
            start_service
        fi
        ;;
    "down")
        echo -e "${YELLOW}Stopping Scene Intelligence service...${NC}"
        docker compose -f $COMPOSE_MAIN down
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}Scene Intelligence service stopped successfully.${NC}"
        else
            echo -e "${RED}Failed to stop services${NC}"
            if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 1; else return 1; fi
        fi
        ;;
    "clean")
        echo -e "${YELLOW}Cleaning up containers, volumes, and images...${NC}"
        docker compose -f $COMPOSE_MAIN down --rmi all --volumes --remove-orphans
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}Cleanup completed successfully.${NC}"
        else
            echo -e "${RED}Cleanup failed${NC}"
            if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 1; else return 1; fi
        fi
        ;;
    "status")
        echo -e "${BLUE}Scene Intelligence Service Status:${NC}"
        docker compose -f $COMPOSE_MAIN ps
        echo ""
        echo -e "${BLUE}Service URLs:${NC}"
        echo -e "  • Scene Intelligence API: ${YELLOW}http://localhost:${SCENE_INTELLIGENCE_PORT}${NC}"
        echo -e "  • AI Route Planner: ${YELLOW}http://localhost:${AI_ROUTE_PLANNER_PORT}${NC}"
        echo -e "  • SceneScape Web: ${YELLOW}https://localhost:${SCENESCAPE_PORT}${NC}"
        echo -e "  • VLM Service: ${YELLOW}http://localhost:${VLM_SERVICE_PORT}${NC}"
        echo -e "  • DL Streamer: ${YELLOW}http://localhost:${DLSTREAMER_PORT}${NC}"
        ;;
    "logs")
        echo -e "${BLUE}==> Service Logs${NC}"
        local follow_flag=""
        if [ "$2" = "--follow" ]; then
            follow_flag="-f"
        fi
        docker compose -f $COMPOSE_MAIN logs $follow_flag
        ;;
    "restart")
        echo -e "${BLUE}==> Restarting services...${NC}"
        docker compose -f $COMPOSE_MAIN down
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}Services stopped successfully${NC}"
            # Check prerequisites first
            check_prerequisites
            if [ $? -eq 0 ]; then
                start_service
            fi
        else
            echo -e "${RED}Failed to stop services${NC}"
            if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 1; else return 1; fi
        fi
        ;;
    "setup")
        full_setup
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo -e "${YELLOW}Use 'help' for usage information${NC}"
        if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 1; else return 1; fi
        ;;
esac

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Done!${NC}"
else
    echo -e "${RED}Operation failed. Check the logs above for details.${NC}"
    if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then exit 1; else return 1; fi
fi
