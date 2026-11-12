"""The model's answer to a validation prompt, as the answer of ``AIProviderPort.validate_query``."""

import json
from typing import Any

from ..ports.ai_provider import checked_validation, validation_unavailable
from ..utils.logger import get_logger

logger = get_logger(__name__)


def validation_from_json(text: str, tokens_used: int) -> dict[str, Any]:
    """Read the model's JSON answer and hold it to the port's contract.

    An answer that cannot be read is a review that was not done. Its tokens are reported
    either way: the call was made.
    """
    try:
        answer = json.loads(text)
    except ValueError as e:
        # The model output can quote user data: DEBUG only
        logger.debug("Validation answer is not JSON", content=text)
        answer = validation_unavailable(f"the model's answer is not JSON ({e})")
    checked = checked_validation(answer)
    checked["_tokens_used"] = tokens_used
    return checked
