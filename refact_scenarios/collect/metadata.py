import json

from datetime import datetime
from pathlib import Path

from .errors import CollectError


class TaskResultMetadata:
    domain: str
    task_name: str
    experiment: str
    model: str
    lsp_version: str
    date: str
    execution_time: float
    chat_max_depth: int


def parse_metadata(passport_file: Path, result_file: Path) -> TaskResultMetadata:
    """
    Parse the metadata from the relevant metadata from the passport.json file.
    """

    metadata = TaskResultMetadata()

    try:
        with open(passport_file, 'r') as f:
            passport = json.load(f)

            metadata.domain = passport["orignal_task"]["domain"]
            metadata.task_name = passport["orignal_task"]["task_name"]
            metadata.experiment = passport["experiment"]
            metadata.model = passport["model"]
            # The first 8 characters of the commit hash should be enough to identify the commit
            metadata.lsp_version = f"{passport['lsp_version']}/{passport['lsp_commit'][0:7]}"
            if "ended_ts" in passport:
                metadata.date = datetime.fromtimestamp(passport["ended_ts"]).strftime("%Y-%m-%d %H:%M:%S")
                metadata.execution_time = passport["ended_ts"] - passport["started_ts"]
            else:
                # This is deprecated and is here only for backwards compatibility, remove in the future
                metadata.date = datetime.fromtimestamp(passport["started_ts"]).strftime("%Y-%m-%d %H:%M:%S")
                metadata.execution_time = result_file.stat().st_mtime - passport["started_ts"]
            # The value should always be present, default is here for backwards compatibility, remove in the future
            metadata.chat_max_depth = passport.get("chat_max_depth", 30)

    except (json.decoder.JSONDecodeError, KeyError, FileNotFoundError) as e:
        raise CollectError("Error parsing passport.json") from e

    return metadata
