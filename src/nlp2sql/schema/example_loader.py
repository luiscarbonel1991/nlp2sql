"""Helper functions for loading and managing examples."""

import json
from pathlib import Path
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger()


def load_default_examples(examples_file: str = "examples/default_examples.json") -> List[Dict[str, Any]]:
    """
    Load default examples from JSON file.

    Args:
        examples_file: Path to examples JSON file (relative to project root)

    Returns:
        List of example dictionaries
    """
    try:
        # Try to find the file relative to the current working directory
        examples_path = Path(examples_file)

        if not examples_path.exists():
            # Try relative to this file's location
            module_dir = Path(__file__).parent.parent.parent
            examples_path = module_dir / examples_file

        if not examples_path.exists():
            logger.warning("Default examples file not found", path=str(examples_path))
            return []

        with open(examples_path) as f:
            examples = json.load(f)

        logger.info("Loaded default examples", count=len(examples), path=str(examples_path))
        return examples

    except Exception as e:
        logger.error("Failed to load default examples", error=str(e))
        return []
