import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)


async def chat_completion(prompt: str, system: str = "", model: str = None) -> str:
    url = f"{settings.lm_studio_url}/v1/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
    }

    logger.info(f"Sending request to LLM Studio: {url}")
    logger.info(f"Prompt length: {len(prompt)} characters")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            result = data["choices"][0]["message"]["content"]

            logger.info(f"LLM response received successfully")
            logger.info(f"Response length: {len(result)} characters")
            logger.debug(f"Full response: {result}")

            return result
    except Exception as e:
        logger.error(f"Error calling LLM: {str(e)}")
        raise


async def check_connectivity() -> bool:
    url = f"{settings.lm_studio_url}/v1/models"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5)
            return resp.status_code == 200
    except Exception:
        return False
