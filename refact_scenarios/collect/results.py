import json

from pathlib import Path

from .errors import CollectError

def parse_json_result_file(file_path: Path):
    """
    Parse the file at the given path and return the biggest JSON, if it exists, as a dictionary.

    Might throw FileNotFoundError, caller is expected to handle that.
    """

    # Might throw FileNotFoundError
    content = open(file_path).read()

    # Find the positions of all '{' and '}' in the string
    opening_braces = [i for i, char in enumerate(content) if char == "{"]
    closing_braces = [i for i, char in enumerate(content) if char == "}"]

    for i in opening_braces:
        for j in reversed(closing_braces):
            if j > i:
                try:
                    return json.loads(content[i : j + 1])
                except json.decoder.JSONDecodeError:
                    continue

    raise json.decoder.JSONDecodeError(msg="No JSON object found", doc=content, pos=0)

def parse_results(result_file: Path):
    """
    Parse the results from the given result file.

    The returned object is the full JSON object from the file.
    """

    try:
        return parse_json_result_file(result_file)
    except (json.decoder.JSONDecodeError, FileNotFoundError) as e:
        raise CollectError("Error parsing result.json") from e
