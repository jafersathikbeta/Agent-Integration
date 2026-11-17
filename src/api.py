"""FastAPI application for the Agent Integration middleware monitor."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

DEFAULT_SENTINEL_URL = "http://127.0.0.1:8000"
DEFAULT_CHATBOT_URL = "http://127.0.0.1:8001"

SETTINGS_PATH = Path(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
) / "Agent_Integration" / "settings.json"


class Settings(BaseModel):
    sentinel_api_url: str = DEFAULT_SENTINEL_URL
    target_chatbot_api_url: str = DEFAULT_CHATBOT_URL


class SimulateRequest(BaseModel):
    simulation_type: Literal["safe", "malicious"]


class SimulateResponse(BaseModel):
    simulation_type: str
    status: Literal["ALLOWED", "BLOCKED", "ERROR"]
    steps: List[str]
    sentinel_response: Optional[Dict[str, Any]] = None
    chatbot_response: Optional[Any] = None
    threat_intel: Optional[Dict[str, Any]] = None
    agent_action: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


app = FastAPI(
    title="Agent Integration",
    description="Middleware monitor and settings dashboard for Sentinel-protected agent flows",
    version="1.0.0",
)


def _load_settings() -> Settings:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return Settings(**data)
        except Exception:
            pass
    return Settings()


def _save_settings(settings: Settings) -> Settings:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        settings.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return settings


def _normalize_base(url: str) -> str:
    return url.rstrip("/")


def _build_safe_action() -> Dict[str, Any]:
    return {
        "agent_id": "agent-integration-monitor",
        "action_type": "READ",
        "target": "docs/user_guide.md",
        "parameters": {"intent": "summarize_document", "simulation": "safe"},
    }


def _build_malicious_action() -> Dict[str, Any]:
    return {
        "agent_id": "agent-integration-monitor",
        "action_type": "EXECUTE",
        "target": "rm -rf /",
        "parameters": {"intent": "destructive_shell", "simulation": "malicious"},
    }


async def _post_json(url: str, payload: Dict[str, Any], timeout: float = 15.0) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, json=payload)


@app.get("/")
async def root():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(index)


@app.get("/api/v1/settings")
async def get_settings():
    return _load_settings()


@app.post("/api/v1/settings")
async def save_settings(settings: Settings):
    saved = _save_settings(settings)
    return {"status": "ok", "settings": saved}


@app.post("/api/v1/simulate", response_model=SimulateResponse)
async def simulate(body: SimulateRequest):
    """
    Run a real middleware simulation against the configured Sentinel and Target Chatbot APIs.

    - safe: AgentAction -> Sentinel (expect 200) -> Chatbot query -> combined trace
    - malicious: AgentAction (rm -rf /) -> Sentinel (expect 403) -> halt before Chatbot
    """
    settings = _load_settings()
    sentinel_base = _normalize_base(settings.sentinel_api_url)
    chatbot_base = _normalize_base(settings.target_chatbot_api_url)
    validate_url = f"{sentinel_base}/api/v1/validate"

    steps: List[str] = []
    action = _build_safe_action() if body.simulation_type == "safe" else _build_malicious_action()

    steps.append("Constructed AgentAction")
    steps.append("Sent to Sentinel")

    try:
        sentinel_resp = await _post_json(validate_url, action)
    except httpx.RequestError as exc:
        steps.append(f"Sentinel unreachable: {exc}")
        return SimulateResponse(
            simulation_type=body.simulation_type,
            status="ERROR",
            steps=steps,
            agent_action=action,
            error=f"Could not reach Sentinel at {validate_url}: {exc}",
        )

    try:
        sentinel_body = sentinel_resp.json()
    except Exception:
        sentinel_body = {"raw": sentinel_resp.text}

    if body.simulation_type == "malicious":
        if sentinel_resp.status_code == 403:
            detail = sentinel_body.get("detail", sentinel_body) if isinstance(sentinel_body, dict) else sentinel_body
            threat = None
            if isinstance(detail, dict):
                threat = detail.get("threat_intel") or detail
                steps.append("Sentinel BLOCKED")
                steps.append("Pipeline halted — Chatbot never contacted")
            else:
                steps.append("Sentinel BLOCKED")
                steps.append("Pipeline halted — Chatbot never contacted")
            return SimulateResponse(
                simulation_type="malicious",
                status="BLOCKED",
                steps=steps,
                sentinel_response=sentinel_body if isinstance(sentinel_body, dict) else {"body": sentinel_body},
                threat_intel=threat if isinstance(threat, dict) else {"detail": detail},
                agent_action=action,
            )

        steps.append(f"Unexpected Sentinel status {sentinel_resp.status_code} (expected 403)")
        return SimulateResponse(
            simulation_type="malicious",
            status="ERROR",
            steps=steps,
            sentinel_response=sentinel_body if isinstance(sentinel_body, dict) else {"body": sentinel_body},
            agent_action=action,
            error=f"Expected Sentinel 403 for malicious action, got {sentinel_resp.status_code}",
        )

    # safe path
    if sentinel_resp.status_code != 200:
        detail = sentinel_body.get("detail", sentinel_body) if isinstance(sentinel_body, dict) else sentinel_body
        threat = detail.get("threat_intel") if isinstance(detail, dict) else None
        steps.append(f"Sentinel rejected safe action ({sentinel_resp.status_code})")
        return SimulateResponse(
            simulation_type="safe",
            status="BLOCKED" if sentinel_resp.status_code == 403 else "ERROR",
            steps=steps,
            sentinel_response=sentinel_body if isinstance(sentinel_body, dict) else {"body": sentinel_body},
            threat_intel=threat if isinstance(threat, dict) else None,
            agent_action=action,
            error=f"Sentinel returned {sentinel_resp.status_code} for safe simulation",
        )

    steps.append("Sentinel ALLOWED")
    steps.append("Sent to Chatbot")

    chat_payload = {
        "message": "Safe simulation query: summarize the user guide section on getting started.",
        "agent_id": action["agent_id"],
        "source": "agent-integration",
    }
    chat_urls = [
        f"{chatbot_base}/api/v1/chat",
        f"{chatbot_base}/chat",
        f"{chatbot_base}/",
    ]

    chatbot_body: Any = None
    last_error: Optional[str] = None
    chat_ok = False

    for chat_url in chat_urls:
        try:
            chat_resp = await _post_json(chat_url, chat_payload)
            try:
                chatbot_body = chat_resp.json()
            except Exception:
                chatbot_body = {"raw": chat_resp.text, "status_code": chat_resp.status_code}

            if chat_resp.status_code < 500:
                chat_ok = True
                steps.append(f"Chatbot responded ({chat_resp.status_code}) via {chat_url}")
                break
            last_error = f"{chat_url} -> HTTP {chat_resp.status_code}"
        except httpx.RequestError as exc:
            last_error = f"{chat_url} -> {exc}"
            continue

    if not chat_ok:
        steps.append("Chatbot unreachable")
        return SimulateResponse(
            simulation_type="safe",
            status="ERROR",
            steps=steps,
            sentinel_response=sentinel_body if isinstance(sentinel_body, dict) else {"body": sentinel_body},
            chatbot_response=chatbot_body,
            agent_action=action,
            error=f"Could not reach Target Chatbot at {chatbot_base}: {last_error}",
        )

    steps.append("Final output ready")
    return SimulateResponse(
        simulation_type="safe",
        status="ALLOWED",
        steps=steps,
        sentinel_response=sentinel_body if isinstance(sentinel_body, dict) else {"body": sentinel_body},
        chatbot_response=chatbot_body,
        agent_action=action,
    )


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
