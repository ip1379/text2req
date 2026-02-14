from pydantic import BaseModel


class EpicGenerateRequest(BaseModel):
    model: str
    input: str = ""
    epic_key: str


class EpicGenerateResponse(BaseModel):
    task_id: str
    status: str = "processing"


class EpicStatusResponse(BaseModel):
    key: str
    status: str
    result: str | None = None
    created_issues: list[str] | None = None


class RequirementsValidateRequest(BaseModel):
    text: str


class RequirementsValidateResponse(BaseModel):
    text: str
    validation: str


class HealthResponse(BaseModel):
    status: str
    jira: str
    lm_studio: str
