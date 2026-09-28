import os
import json
import re
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from hindsight_client import Hindsight

load_dotenv()

app = FastAPI(title="Incident Response Agent")

hindsight = Hindsight(
    base_url=os.environ["HINDSIGHT_URL"],
    api_key=os.environ["HINDSIGHT_API_KEY"],
)

BANK_ID = os.environ["HINDSIGHT_BANK_ID"]


class Incident(BaseModel):
    service: str
    symptoms: str
    error: str | None = None
    root_cause: str
    fix: str
    verification: str


class InvestigationRequest(BaseModel):
    description: str = Field(min_length=1)


class InvestigationRecommendation(BaseModel):
    summary: str
    likely_root_causes: list[str]
    recommended_actions: list[str]
    verification_steps: list[str]
    confidence: str
    evidence: list[str]


class InvestigationResponse(BaseModel):
    query: str
    memories_recalled: int
    recommendation: InvestigationRecommendation


def _field_values(memories: list[str], field: str) -> list[str]:
    values = []
    pattern = re.compile(rf"^{re.escape(field)}:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    for memory in memories:
        match = pattern.search(memory)
        if match:
            value = match.group(1).strip()
            if value and value.lower() != "not provided":
                values.append(value)
    return _unique(values)


def _unique(values: list[str], limit: int = 3) -> list[str]:
    result = []
    seen = set()
    for value in values:
        normalized = value.casefold()
        if normalized not in seen:
            seen.add(normalized)
            result.append(value)
        if len(result) == limit:
            break
    return result


def _deterministic_recommendation(memories: list[str]) -> InvestigationRecommendation:
    root_causes = _field_values(memories, "Root cause")
    actions = _field_values(memories, "Fix")
    verification = _field_values(memories, "Verification")
    evidence = [
        " ".join(memory.split())[:240]
        for memory in memories[:3]
        if memory.strip()
    ]

    if memories:
        summary = (
            f"Found {len(memories)} related incident "
            f"{'memory' if len(memories) == 1 else 'memories'}. "
            "Start with the recurring root cause and validate the matching fix."
        )
        confidence = "medium" if len(memories) > 1 else "low"
    else:
        summary = "No related incident memories were found; investigate from current telemetry."
        confidence = "low"

    return InvestigationRecommendation(
        summary=summary,
        likely_root_causes=root_causes or ["No prior root cause was recorded."],
        recommended_actions=actions or ["Collect logs, metrics, and recent deployment changes."],
        verification_steps=verification or ["Confirm recovery in health metrics and service logs."],
        confidence=confidence,
        evidence=evidence,
    )


def _llm_recommendation(query: str, memories: list[str]) -> InvestigationRecommendation | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not memories:
        return None

    try:
        from openai import OpenAI

        client_options = {"api_key": api_key}
        if base_url := os.getenv("OPENAI_BASE_URL"):
            client_options["base_url"] = base_url
        client = OpenAI(**client_options)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            instructions=(
                "You are an incident-response assistant. Return only valid JSON with "
                "the keys summary, likely_root_causes, recommended_actions, "
                "verification_steps, confidence, and evidence. Each list must contain "
                "at most 3 concise strings. Use only the supplied memories; do not "
                "invent facts or include secrets."
            ),
            input=json.dumps({"incident": query, "memories": memories[:5]}),
        )
        payload: Any = json.loads(response.output_text)
        return InvestigationRecommendation.model_validate(payload)
    except Exception:
        return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/incidents")
def record_incident(incident: Incident):
    content = (
        f"Service: {incident.service}\n"
        f"Symptoms: {incident.symptoms}\n"
        f"Error: {incident.error or 'Not provided'}\n"
        f"Root cause: {incident.root_cause}\n"
        f"Fix: {incident.fix}\n"
        f"Verification: {incident.verification}"
    )

    try:
        hindsight.retain(
            bank_id=BANK_ID,
            content=content,
        )
        return {"status": "stored", "service": incident.service}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not store incident in Hindsight.",
        ) from exc


@app.post("/investigate", response_model=InvestigationResponse)
def investigate(request: InvestigationRequest):
    try:
        result = hindsight.recall(
            bank_id=BANK_ID,
            query=request.description,
        )

        memories = [
            memory.text
            for memory in result.results
            if isinstance(memory.text, str) and memory.text.strip()
        ]
        recommendation = _llm_recommendation(request.description, memories)

        return InvestigationResponse(
            query=request.description,
            memories_recalled=len(memories),
            recommendation=recommendation or _deterministic_recommendation(memories),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not recall incidents from Hindsight.",
        ) from exc