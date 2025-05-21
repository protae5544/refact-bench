import pandas as pd

from pathlib import Path

from refact_scenarios.fakeide_logging import global_logger
from .chat_analytics import parse_chat_analytics
from .errors import CollectError, ExperimentMismatchError
from .metadata import parse_metadata
from .results import parse_results

def collect_task_results(subdir: Path, experiment: str):
    task_json = subdir / "task.json"
    result_json = subdir / "result.json"
    passport_json = subdir / "passport.json"

    # Get metadata
    task_metadata = parse_metadata(passport_json, result_json)
    # Get results
    task_results = parse_results(result_json)
    # Get chat analytics 
    chat_analytics = parse_chat_analytics(task_json)

    if task_metadata.experiment != experiment:
        raise ExperimentMismatchError("Experiment mismatch. Expected %s, got %s" % (experiment, task_metadata.experiment))

    worked_status = "✅" if task_results["worked"] == "YES" else "❌"
    del task_results["worked"]

    result = {
        # Metadata
        "domain": task_metadata.domain,
        "task_name": task_metadata.task_name,
        "model": task_metadata.model,
        "lsp_version": task_metadata.lsp_version,
        "execution_time": "%.1f" % task_metadata.execution_time,
        "date": task_metadata.date,
        "chat_max_depth": task_metadata.chat_max_depth,
        # Results
        "worked": worked_status,
        "details": task_results,
        # Token usage
        "tokens (prompt/completion)": chat_analytics.token_usage.legacy_token_str(),
        "prompt_tokens": chat_analytics.token_usage.prompt_tokens,
        "completion_tokens": chat_analytics.token_usage.completion_tokens,
        "cache_read_input_tokens": chat_analytics.token_usage.cache_read_input_tokens,
        "cache_creation_input_tokens": chat_analytics.token_usage.cache_creation_input_tokens,
        # Chat analytics
        "chat_depth": chat_analytics.chat_depth,
        "chat_tool_usage": chat_analytics.tool_usage
    }

    return result

def collect_table_results(workspace_dir: Path, experiment: str, sensitive: bool = False):
    """
    Collect the results from the tasks in the workspace directory and save them to a csv file in results directory.

    Task with a different experiment name will be skipped.

    If sensitive is True, errors will be raised instead of logged.
    """
    results = []
    skipped = 0
    for subdir in sorted(workspace_dir.iterdir()):
        if not subdir.is_dir():
            continue

        try:
            task_results = collect_task_results(subdir, experiment)
            results.append(task_results)
        except ExperimentMismatchError as e:
            global_logger.debug("Skipping %s: %s" % (subdir, e))
            skipped += 1
        except CollectError as e:
            global_logger.error("Error on task %s: %s" % (subdir.stem, e))
            if sensitive:
                return 1

    if skipped > 0:
        global_logger.info("Skipped %d tasks" % skipped)

    df = pd.DataFrame(results)
    global_logger.info(df)
    
    results_dir = Path(__file__).parent.parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    df.to_csv(results_dir / ("%s.csv" % experiment), index=False)

    return 0
