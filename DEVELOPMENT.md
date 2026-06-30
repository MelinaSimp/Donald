# Donald Development Guide

This document covers setting up and running the Donald agent with the Golden Amber Orb UI.

## Architecture

The Donald system consists of two components:

1. **Python Backend** (`donald/` + API server): The agent logic powered by Claude
2. **Next.js Frontend** (`web/`): The Golden Amber Orb UI

They communicate via HTTP with the backend running on `http://localhost:8000` and the frontend on `http://localhost:3000`.

## Prerequisites

- Python 3.10+
- Node.js 18+
- `ANTHROPIC_API_KEY` environment variable set

## Quick Start

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Node Dependencies

```bash
cd web
npm install
```

### 3. Start the Backend Server

In the project root:

```bash
python -m uvicorn web.api.agent:app --host 127.0.0.1 --port 8000 --reload
```

Or use the convenience script:

```bash
python web/api/agent.py
```

### 4. Start the Frontend Development Server

In the `web/` directory:

```bash
npm run dev
```

### 5. Open in Browser

Navigate to http://localhost:3000

## Usage

1. Boot animation plays automatically
2. Click the golden orb to show the input prompt
3. Type your message and press Enter or click SEND
4. Donald processes your request and responds with his characteristic flair

## Environment Variables

- `ANTHROPIC_API_KEY`: Required for Claude API access
- `DONALD_API_URL`: Backend URL (defaults to `http://localhost:8000`)

## Development Notes

### Modifying the Agent

The agent personality and behavior are controlled by:

- `donald/AGENT.md`: The personality definition
- `donald/personality.py`: Personality persistence logic
- `donald/agent.py`: Agent loop logic

Changes to the agent behavior require restarting the backend server.

### Modifying the UI

The UI component is in `web/components/DonaldOrb.tsx`. It's a React component with:

- Canvas-based golden amber orb animation
- State transitions (idle → listening → thinking → speaking)
- Interactive input handling
- Real-time API communication

Frontend changes hot-reload automatically during development.

## Production Build

### Frontend

```bash
cd web
npm run build
npm start
```

### Backend

Use a production ASGI server like Gunicorn with Uvicorn workers:

```bash
gunicorn web.api.agent:app --workers 4 --worker-class uvicorn.workers.UvicornWorker
```

## Testing

### Python Tests

```bash
pytest
```

### Frontend Tests (when applicable)

```bash
cd web
npm test
```

## API Endpoints

- `POST /chat` - Send a message to Donald
  - Request: `{ "text": "Your message" }`
  - Response: `{ "response": "Donald's response", "state": "speaking" }`
- `POST /reset` - Reset conversation state
- `GET /health` - Health check

## Troubleshooting

### Backend won't start

- Ensure `ANTHROPIC_API_KEY` is set
- Check that port 8000 is available
- Verify FastAPI is installed: `pip install fastapi uvicorn`

### Frontend can't reach backend

- Ensure backend is running on `http://localhost:8000`
- Check browser console for CORS or connection errors
- Set `DONALD_API_URL` environment variable if backend is on different host

### Agent not responding

- Check that Anthropic API key is valid
- Monitor backend logs for API errors
- Try resetting the conversation with POST `/reset`
