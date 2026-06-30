"""FastAPI server for the Donald agent.

Wraps the agent logic to expose it via HTTP, maintaining the personality-persistence
layer through API state management.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from donald.conversation import ConversationManager
from donald.personality import append_voice_cue, build_system_prompt, load_personality


class MessageRequest(BaseModel):
    text: str


class MessageResponse(BaseModel):
    response: str
    state: str


class ResetRequest(BaseModel):
    pass


# Global agent state (for development; in production use proper session management)
_conversation: Optional[ConversationManager] = None
_personality: Optional[str] = None
_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize agent on startup."""
    global _conversation, _personality, _client

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Set ANTHROPIC_API_KEY to start the server.")

    from anthropic import Anthropic

    _client = Anthropic()
    _conversation = ConversationManager()
    _personality = load_personality()

    yield


app = FastAPI(title="Donald Agent API", lifespan=lifespan)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat", response_model=MessageResponse)
async def chat(request: MessageRequest) -> MessageResponse:
    """Send a message to Donald and get a response."""
    if not _conversation or not _personality or not _client:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    # Add user message
    _conversation.add_user_message(request.text)

    # Build API payload
    messages = _conversation.messages_for_api()
    append_voice_cue(messages)
    system = build_system_prompt(_personality)

    # Call Claude
    response = _client.messages.create(
        model="claude-opus-4-8",
        system=system,
        messages=messages,
        max_tokens=1024,
        temperature=0.8,
    )

    # Extract response text
    text = "".join(b.text for b in response.content if b.type == "text")
    _conversation.add_assistant_message(text)

    return MessageResponse(response=text, state="speaking")


@app.post("/reset")
async def reset(request: ResetRequest = None) -> dict:
    """Reset the conversation state."""
    global _conversation
    if not _personality or not _client:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    _conversation = ConversationManager()
    return {"status": "reset"}


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
