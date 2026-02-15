import httpx
import logging
from config import settings

logger = logging.getLogger(__name__)


def _text_to_adf(text: str) -> dict:
    """
    Convert plain text with newlines to Jira's Atlassian Document Format (ADF).
    Splits text by newlines and creates separate paragraph nodes.
    """
    if not text:
        return {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": []
                }
            ]
        }

    # Split by newlines and create paragraph for each line
    lines = text.split('\n')
    paragraphs = []

    for line in lines:
        # Create paragraph even for empty lines to preserve spacing
        paragraphs.append({
            "type": "paragraph",
            "content": [
                {"type": "text", "text": line}
            ] if line.strip() else []  # Empty content for blank lines
        })

    return {
        "version": 1,
        "type": "doc",
        "content": paragraphs
    }


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }


async def _get_authenticated_client() -> httpx.AsyncClient:
    """
    Create an authenticated httpx client.
    Uses Bearer token authentication for Personal Access Tokens (PAT).
    """
    headers = _headers()
    # Add Bearer token authentication header
    headers["Authorization"] = f"Bearer {settings.jira_api_token}"

    logger.info(f"Headers being used: {headers}")
    logger.info(f"Token (first 20 chars): {settings.jira_api_token[:20]}...")

    client = httpx.AsyncClient(headers=headers, timeout=60)
    logger.info(f"Created authenticated client for Jira user: {settings.jira_email}")
    return client


async def get_epic(epic_key: str) -> dict:
    base_url = settings.jira_base_url.rstrip('/')
    url = f"{base_url}/rest/api/2/issue/{epic_key}"
    client = await _get_authenticated_client()
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    finally:
        await client.aclose()


async def add_comment(issue_key: str, body: str) -> dict:
    base_url = settings.jira_base_url.rstrip('/')
    url = f"{base_url}/rest/api/2/issue/{issue_key}/comment"
    payload = {"body": _text_to_adf(body)}
    client = await _get_authenticated_client()
    try:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
    finally:
        await client.aclose()


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
    issue_type: str = "Aufgabe",
    parent_key: str = None
) -> dict:
    """
    Create a new Jira issue.

    Args:
        project_key: The Jira project key (e.g., "PROJ")
        summary: Issue title/summary
        description: Issue description
        issue_type: Type of issue (Aufgabe, etc.)
        parent_key: Optional parent epic key for Epic Link

    Returns:
        Created issue data including the new issue key
    """
    base_url = settings.jira_base_url.rstrip('/')
    url = f"{base_url}/rest/api/2/issue"

    # MINIMAL PAYLOAD - Only absolutely required fields
    # We'll add optional fields via update after creation
    payload = {
        "fields": {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,  # Required field
        }
    }

    # Set reporter to the configured user
    payload["fields"]["reporter"] = {"name": settings.jira_email}
    logger.info(f"Set reporter to: {settings.jira_email}")

    logger.info(f"Creating Jira issue: {summary[:50]}...")
    logger.info(f"Project: {project_key}, Type: {issue_type}, Parent: {parent_key}")
    logger.debug(f"Full payload: {payload}")

    client = await _get_authenticated_client()
    try:
        resp = await client.post(url, json=payload)

        # Log detailed error information if request fails
        if resp.status_code >= 400:
            logger.error(f"=" * 80)
            logger.error(f"JIRA API ERROR - Status: {resp.status_code}")
            logger.error(f"URL: {url}")
            logger.error(f"-" * 80)
            logger.error(f"Response body:\n{resp.text}")
            logger.error(f"-" * 80)
            logger.error(f"Request payload:\n{payload}")
            logger.error(f"=" * 80)

            # Try to parse error message from Jira
            try:
                error_data = resp.json()
                if "errorMessages" in error_data:
                    logger.error(f"Jira error messages: {error_data['errorMessages']}")
                if "errors" in error_data:
                    logger.error(f"Jira field errors: {error_data['errors']}")
            except:
                pass

        resp.raise_for_status()
        created_issue = resp.json()

        # Now update the issue with fields that aren't on the create screen
        issue_key = created_issue.get("key")
        if issue_key:
            update_payload = {"fields": {}}
            has_updates = False

            # Add description if provided (using fields format - Jira Server compatible)
            if description:
                # For Jira Server, use plain text instead of ADF
                update_payload["fields"]["description"] = description
                has_updates = True

            # Add epic link if provided (using fields format)
            if parent_key:
                if issue_type.lower() == "sub-task":
                    update_payload["fields"]["parent"] = {"key": parent_key}
                else:
                    update_payload["fields"]["customfield_10100"] = parent_key
                has_updates = True

            # Update the issue if we have fields to update
            if has_updates:
                logger.info(f"Updating issue {issue_key} with additional fields...")
                update_url = f"{base_url}/rest/api/2/issue/{issue_key}"
                update_resp = await client.put(update_url, json=update_payload)
                if update_resp.status_code >= 400:
                    logger.error(f"Failed to update issue {issue_key}: {update_resp.text}")
                    logger.error(f"Update payload: {update_payload}")
                else:
                    logger.info(f"Successfully updated issue {issue_key}")

        return created_issue
    finally:
        await client.aclose()


async def check_connectivity() -> bool:
    logger.info("Starting Jira connectivity check...")
    base_url = settings.jira_base_url.rstrip('/')
    url = f"{base_url}/rest/api/2/myself"
    logger.info(f"Checking URL: {url}")
    try:
        logger.info("Creating authenticated client...")
        client = await _get_authenticated_client()
        try:
            logger.info("Sending GET request to Jira...")
            resp = await client.get(url, timeout=10)
            logger.info(f"Jira connectivity check: {resp.status_code}")
            return resp.status_code == 200
        finally:
            await client.aclose()
    except Exception as e:
        logger.error(f"Jira connectivity check failed: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
