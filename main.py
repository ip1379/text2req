import logging
import sys
import uuid

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from config import settings

# Configure logging to output to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
from models import (
    EpicGenerateRequest,
    EpicGenerateResponse,
    EpicStatusResponse,
    HealthResponse,
    RequirementsValidateRequest,
    RequirementsValidateResponse,
)
from services import jira_service, llm_service

app = FastAPI(title="Jira ↔ LM Studio Intermediary")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error for {request.url}")
    logger.error(f"Request body: {await request.body()}")
    logger.error(f"Validation errors: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


# In-memory task tracker: task_id -> {key, status, result}
tasks: dict[str, dict] = {}


async def _process_epic(task_id: str, epic_key: str, input_text: str, model: str = None) -> None:
    try:
        logger.info(f"Processing epic {epic_key} with input: {input_text[:100]}...")

        # Extract project key from epic_key (e.g., "PROJ-123" -> "PROJ")
        project_key = epic_key.split("-")[0]

        # Use the input text directly instead of fetching from Jira
        prompt = (
            f"Input: {input_text}\n\n"
            "Based on this input, generate a detailed breakdown as a JSON array.\n"
            "Each item should have:\n"
            '- "summary": A clear, concise title (max 100 chars)\n'
            '- "description": Detailed description with acceptance criteria\n'
            '- "issue_type": Either "Story", "Task", or "Bug"\n\n'
            "Return ONLY valid JSON array, no additional text.\n"
            "Example format:\n"
            '[\n'
            '  {\n'
            '    "summary": "Implement user login",\n'
            '    "description": "As a user, I want to log in...\\n\\nAcceptance Criteria:\\n- ...",\n'
            '    "issue_type": "Story"\n'
            '  }\n'
            ']'
        )

        logger.info(f"Generated prompt for LLM with length {len(prompt)}")

        result = await llm_service.chat_completion(
            prompt,
            system="You are a senior product manager and technical lead. Generate structured, actionable epic breakdowns as valid JSON only.",
            model=model
        )

        logger.info(f"Output from LLM: {result[:100]}")

        # Parse JSON and create Jira issues
        import json
        issues_data = json.loads(result.strip())

        logger.info(f"Creating {len(issues_data)} Jira issues under epic {epic_key}")
        created_issues = await jira_service.create_bulk_issues(
            project_key=project_key,
            issues_data=issues_data,
            parent_key=epic_key
        )

        # Store both the LLM result and created issue keys
        issue_keys = [issue.get("key") for issue in created_issues]
        tasks[task_id] = {
            "key": epic_key,
            "status": "completed",
            "result": result,
            "created_issues": issue_keys
        }
        logger.info(f"Successfully processed epic {epic_key}, created issues: {issue_keys}")
    except Exception as exc:
        logger.error(f"Failed to process epic {epic_key}: {str(exc)}")
        tasks[task_id] = {"key": epic_key, "status": "failed", "result": str(exc)}


@app.post("/api/v1/jira/epic/generate")
async def generate_epic(req: EpicGenerateRequest, background_tasks: BackgroundTasks):
    logger.info(f"received request to generate epic breakdown for {req.epic_key} with context length {len(req.input)}")
    logger.info(f"Full request: {req}")

    task_id = str(uuid.uuid4())
    background_tasks.add_task(_process_epic, task_id, req.epic_key, req.input, req.model)
    return EpicGenerateResponse(task_id=task_id, status="processing")


@app.get("/api/v1/jira/epic/{key}/status", response_model=EpicStatusResponse)
async def epic_status(key: str):
    for entry in tasks.values():
        if entry["key"] == key:
            return EpicStatusResponse(**entry)
    return EpicStatusResponse(key=key, status="not_found")


@app.post("/api/v1/requirements/validate", response_model=RequirementsValidateResponse)
async def validate_requirements(req: RequirementsValidateRequest):
    prompt = (
        f"Evaluate the following requirement:\n\n{req.text}\n\n"
        "Assess it for:\n"
        "1. Clarity — is it unambiguous?\n"
        "2. Completeness — are acceptance criteria implied or missing?\n"
        "3. Testability — can QA write tests from this?\n\n"
        "Provide a short verdict and suggestions for improvement."
    )
    result = await llm_service.chat_completion(
        prompt,
        system="You are a requirements analyst. Be concise and actionable.",
    )
    return RequirementsValidateResponse(text=req.text, validation=result)


@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    jira_ok = await jira_service.check_connectivity()
    llm_ok = await llm_service.check_connectivity()
    overall = "healthy" if (jira_ok and llm_ok) else "degraded"
    return HealthResponse(
        status=overall,
        jira="connected" if jira_ok else "unreachable",
        lm_studio="connected" if llm_ok else "unreachable",
    )
