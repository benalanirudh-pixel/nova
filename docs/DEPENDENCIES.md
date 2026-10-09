# Dependencies

Last audited: 2026-10-09.

There is currently no `requirements.txt`, `pyproject.toml`, or package lock
file in the project root. Dependency evidence comes from imports and
`.\venv\Scripts\python.exe -m pip freeze`.

## Runtime Interpreter

Use:

```powershell
.\venv\Scripts\python.exe
```

The inspected environment contains Python 3.14 package builds based on wheel
tags and installed package paths.

## Important Installed Packages

The existing `venv/` includes:

- UI and desktop: `PySide6`, `PyOpenGL`, `psutil`, `pywin32`
- Local LLM: `ollama`
- Data: `pandas`, `numpy`, `yfinance`, `requests`, `curl_cffi`,
  `beautifulsoup4`, `lxml`, `openpyxl`
- Voice/STT/TTS: `faster-whisper`, `ctranslate2`, `sounddevice`, `silero-vad`,
  `piper-tts`, `onnxruntime`, `torch`
- Market MCP: `mcp`, `indian-market-mcp`
- Web/server utilities present in the environment: `httpx`, `uvicorn`,
  `starlette`, `websockets`

## Local Assets

These are not ordinary Python dependencies but are required by runtime paths:

- `voices/en_US-lessac-high.onnx`
- `voices/en_US-lessac-high.onnx.json`
- `stt_models/models--Systran--faster-whisper-small/.../model.bin`

## External Services

- Ollama local server for chat and Market Lab interpretation.
- Ollama model `qwen3.5:4b`.
- Optional local SearXNG at `http://localhost:8080`.
- Public market-data endpoints used by NSE/Yahoo/source-specific engines.

## Reproducibility Gap

Because there is no dependency manifest, a future cleanup task should create a
minimal `requirements.txt` or `pyproject.toml` from the runtime actually needed
by source files. Do not blindly freeze the whole environment into a production
manifest without reviewing whether each package is truly required.
