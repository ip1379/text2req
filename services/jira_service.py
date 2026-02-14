import httpx
from config import settings


def _auth() -> httpx.BasicAuth:
    return httpx.BasicAuth(settings.jira_email, settings.jira_api_token)


def _headers() -> dict[str, str]:
    return {"Accept": "application/json", "Content-Type": "application/json"}


async def get_epic(epic_key: str) -> dict:
    base_url = settings.jira_base_url.rstrip('/')
    url = f"{base_url}/rest/api/2/issue/{epic_key}"
    async with httpx.AsyncClient(auth=_auth(), headers=_headers()) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def add_comment(issue_key: str, body: str) -> dict:
    base_url = settings.jira_base_url.rstrip('/')
    url = f"{base_url}/rest/api/2/issue/{issue_key}/comment"
    payload = {
        "body": {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": body}],
                }
            ],
        }
    }
    async with httpx.AsyncClient(auth=_auth(), headers=_headers()) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def create_bulk_issues(
    project_key: str,
    issues_data: list[dict],
    parent_key: str = None
) -> list[dict]:
    """
    Create multiple Jira issues from a list.

    Args:
        project_key: The Jira project key
        issues_data: List of dicts with 'summary', 'description', 'issue_type'
        parent_key: Optional parent epic key

    Returns:
        List of created issue responses
    """
    created_issues = []
    for issue in issues_data:
        result = await create_issue(
            project_key=project_key,
            summary=issue.get("summary", ""),
            description=issue.get("description", ""),
            issue_type=issue.get("issue_type", "Task"),
            parent_key=parent_key
        )
        created_issues.append(result)
    return created_issues


async def create_issue(
    project_key: str,
    summary: str,
    description: str,
    issue_type: str = "Task",
    parent_key: str = None
) -> dict:
    """
    Create a new Jira issue.

    Args:
        project_key: The Jira project key (e.g., "PROJ")
        summary: Issue title/summary
        description: Issue description
        issue_type: Type of issue (Task, Story, Bug, Sub-task, etc.)
        parent_key: Optional parent epic/story key for sub-tasks

    Returns:
        Created issue data including the new issue key
    """
    base_url = settings.jira_base_url.rstrip('/')
    url = f"{base_url}/rest/api/2/issue"

    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {
                "version": 1,
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            },
            "issuetype": {"name": issue_type},
        }
    }

    # Add parent link if creating a sub-task
    if parent_key:
        payload["fields"]["parent"] = {"key": parent_key}

    async with httpx.AsyncClient(auth=_auth(), headers=_headers()) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def check_connectivity() -> bool:
    base_url = settings.jira_base_url.rstrip('/')
    url = f"{base_url}/rest/api/2/myself"
    try:
        async with httpx.AsyncClient(auth=_auth(), headers=_headers()) as client:
            resp = await client.get(url, timeout=10)
            return resp.status_code == 200
    except Exception:
        return False
