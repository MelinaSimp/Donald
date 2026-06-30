#!/bin/bash

# Donald Development Startup Script
# Starts both the Python backend and Node.js frontend

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🎭 Donald - Starting development environment${NC}\n"

# Check for ANTHROPIC_API_KEY
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY environment variable not set"
    exit 1
fi

# Start backend
echo -e "${GREEN}▶ Starting backend server...${NC}"
python -m uvicorn web.api.agent:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# Give backend time to start
sleep 2

# Check if backend started successfully
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "Failed to start backend"
    exit 1
fi

echo -e "${GREEN}✓ Backend started (PID: $BACKEND_PID)${NC}"

# Start frontend
echo -e "${GREEN}▶ Starting frontend server...${NC}"
cd web
npm run dev &
FRONTEND_PID=$!

echo -e "${GREEN}✓ Frontend starting...${NC}"
echo -e "${BLUE}Frontend: http://localhost:3000${NC}"
echo -e "${BLUE}Backend: http://localhost:8000${NC}\n"

# Cleanup on exit
cleanup() {
    echo -e "\n${BLUE}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo "Done"
}

trap cleanup EXIT

# Wait for both processes
wait
