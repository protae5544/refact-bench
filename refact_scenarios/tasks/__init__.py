from pathlib import Path
from datetime import datetime

import refact
from refact_scenarios.fakeide_logging import global_logger
from refact_scenarios.fakeide_static_lsp import get_static_lsp_last_modified_time
from refact_scenarios.fakeide_utils import get_workspace_dir
from refact_scenarios.tasks.validator import get_tasks
from refact_scenarios.tasks.orchestrator import process_tasks

def get_lsp_bin():
    """
    Get the path to the lsp binary.
    """
    lsp_bin_candidates = [  
        Path(refact.__file__).parent.parent.parent / "target" / "debug" / "refact-lsp",
        Path(refact.__file__).parent.parent.parent / "target" / "release" / "refact-lsp",
        Path(refact.__file__).parent / "bin" / "refact-lsp",
        Path.home() / ".cache" / "refact" / "refact-lsp",
    ]
    lsp_bin = None
    for path in lsp_bin_candidates:
        if path.exists():
            lsp_bin = path
            break
    if lsp_bin is None:
        global_logger.error(f"No valid path found. Tried: {','.join(map(str, lsp_bin_candidates))}")
        raise Exception("LSP binary not found. Please compile it first.")

    return lsp_bin

async def run_tasks(args):
    if args.cli and args.parallel_jobs > 1:
        global_logger.error("Cannot start CLI with parallel jobs.")
        return 1

    workspace_dir = get_workspace_dir(args)
    lsp_bin = get_lsp_bin()

    # Log the last modified time of the lsp binaries
    last_modified_time = datetime.fromtimestamp(lsp_bin.stat().st_mtime)
    time_diff = datetime.now() - last_modified_time
    global_logger.debug("binary path: %s (compiled %.1f hours ago)" % (lsp_bin, time_diff.total_seconds() / 3600))
    if args.docker:
        static_lsp_last_modified_time = get_static_lsp_last_modified_time()
        time_diff = datetime.now() - static_lsp_last_modified_time
        global_logger.debug("static lsp binary compiled %.1f hours ago" % (time_diff.total_seconds() / 3600))

    # Get the tasks that are going to be run
    tasks = get_tasks(
        tasks_path=args.task,
        workspace_dir=workspace_dir,
        experiment=args.experiment,
        rerun_all=args.rerun_all,
        max_task_amount=args.amount,
    )

    if len(tasks) == 0:
        global_logger.info("No tasks to run.")
        return 0

    global_logger.info(f"Running {len(tasks)} tasks.")

    return await process_tasks(
        tasks,
        workspace_dir=workspace_dir,
        lsp_bin=lsp_bin,
        model=args.model,
        boost_thinking=args.boost_thinking,
        cli_start=args.cli,
        cli_start_with=args.cli_start_with,
        run_in_docker=args.docker,
        rebuild_image=args.rebuild_image,
        experiment=args.experiment,
        address_url=args.address_url,
        api_key=args.api_key,
        chat_max_depth=args.chat_max_depth,
        parallel_jobs=args.parallel_jobs,
        cache=args.cache_level,
        ignore_errors=args.ignore_errors,
    )
