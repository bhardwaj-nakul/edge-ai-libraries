#!/bin/bash

# RSU Monitoring System Startup Script
echo "Starting RSU Monitoring System..."

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
uv pip install -r requirements.txt

# Run the application
echo "Starting Gradio application..."
python3 app.py