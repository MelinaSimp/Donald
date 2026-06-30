#!/usr/bin/env bash
# Launch the reference voice agent. Runs fully offline by default (mock LLM +
# mock TTS) so you can see the pipeline working with no API keys.
#
#   ./run.sh                 # mock everything, open http://localhost:8000
#   ANTHROPIC_API_KEY=... ./run.sh        # real Claude streaming, mock TTS
#   TTS_PROVIDER=openai OPENAI_API_KEY=... ./run.sh   # + real streaming TTS
set -euo pipefail
cd "$(dirname "$0")"
exec uvicorn server.app:app --reload --port "${PORT:-8000}"
