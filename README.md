# Agent Integration Monitor

A desktop middleware monitor and simulation dashboard for securing AI agent actions. This tool intercepts agent workflows, validates intent against a Sentinel API, and dynamically routes safe queries to downstream LLM chatbots while actively blocking malicious commands.

## Architecture & Workflow

- **Desktop App:** Native window provided by `pywebview`.
- **Backend:** Local `FastAPI` server managing request routing and simulation logic.
- **Networking:** Utilizes `httpx` for asynchronous HTTP communication with external Sentinel and Chatbot APIs.

### Simulation Flow

1. **Construct Action:** The dashboard builds either a Safe (`READ` docs) or Malicious (`EXECUTE rm -rf /`) `AgentAction` payload.
2. **Sentinel Validation:** The action is sent to the configured Sentinel API.
   - **Malicious path:** Sentinel returns `403 Forbidden`. The pipeline halts immediately, and the threat intelligence is logged.
   - **Safe path:** Sentinel returns `200 OK`. The action is forwarded to the target Chatbot.
3. **Chatbot Response:** Safe queries receive a generative response from the downstream chatbot API, completing the trace.

## Features

- **Dynamic Configuration:** Set target URLs for both Sentinel and Chatbot APIs directly from the UI. Settings are securely stored in `%LOCALAPPDATA%\Agent_Integration\settings.json`.
- **Real-time Tracing:** Watch the exact steps of the middleware pipeline (`Constructed AgentAction` -> `Sent to Sentinel` -> `BLOCKED/ALLOWED`).
- **Error Boundary Handling:** Gracefully handles unreachable servers, displaying detailed HTTPX errors in the trace.

## Setup & Installation (Windows)

1. Clone the repository and create a virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Run the application:
   ```powershell
   python run.py
   ```
   *This starts the FastAPI server on port 8020 and launches the pywebview desktop window.*

## Dependencies

- **UI/Server:** `fastapi`, `uvicorn`, `pywebview`, `pydantic`
- **Networking:** `httpx`, `requests`
- **Build/OS Integration:** `pyinstaller`, `pywin32`, `winshell`