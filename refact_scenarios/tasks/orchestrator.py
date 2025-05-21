import asyncio
import os
import docker
import random
import traceback

from pathlib import Path
from typing import List, Optional, Tuple

from refact_scenarios.fakeide_docker import load_isolation_config
from refact_scenarios.fakeide_logging import task_logger, global_logger
from refact_scenarios.fakeide_structs import IntegrationIsolation, Task
from refact_scenarios.fakeide_utils import git_clone_to_rev
from refact_scenarios.tasks.docker import get_docker_client, build_docker_image_if_needed, docker_compose_action
from refact_scenarios.tasks.runner import run_task_internal

async def run_single_task(
    task_dir: Path,
    task_rec: Task,
    workspace_dir: Path,
    lsp_bin: str,
    address_url: str,
    run_in_docker: bool,
    experiment: str,
    api_key: str,
    rebuild_image: bool,

    model: str,
    boost_thinking: bool,
    cli_start: bool,
    cli_start_with: str,
    chat_max_depth: int,

    log_to_console: bool,
    cache_level: int,
):
    """
    Create task_workdir
    Create logger
    Generate chat_id
    Populate task_workdir
    Build docker image if needed
    Run dependency docker-compose up if needed
    Run the task
    Clean up docker image if needed
    Clean up docker-compose if needed
    """
    global_logger.info(f"Starting task {task_rec.make_task_name()}")

    # Create task_workdir
    task_workdir = workspace_dir / task_rec.make_task_name()
    os.makedirs(task_workdir, exist_ok=True)

    # Create logger
    logger = task_logger(task_rec.make_task_name(), task_workdir, running_only_one_task=log_to_console)

    try:
        # Generate chat_id
        chat_id = "fakeide-" + "".join(random.choices("0123456789abcdef", k=10))
        # Populate task_workdir
        await git_clone_to_rev(task_rec, task_workdir / task_rec.repo_underscores(), logger)

        # Build docker image if needed
        isolation_config: Optional[IntegrationIsolation] = None
        image_id: Optional[str] = None
        if run_in_docker:
            assert task_rec.integrations_yaml is not None
            isolation_config = load_isolation_config(
                task_dir / task_rec.integrations_yaml, 
                task_dir / task_rec.variables_yaml if task_rec.variables_yaml is not None else None,
            )
            image_id = await build_docker_image_if_needed(
                task_rec=task_rec,
                repo_path=task_workdir / task_rec.repo_underscores(),
                task_dir=task_dir,
                rebuild_image=rebuild_image,
                isolation_config=isolation_config,
                cache=(cache_level >= 2),
                logger=logger,
            )
            # Run dependency docker-compose up if needed
            if task_rec.docker_compose_dependencies_yaml is not None:
                await docker_compose_action(task_dir / task_rec.docker_compose_dependencies_yaml, "up")

        try:
            # Run the task
            await run_task_internal(
                task_dir=task_dir,
                task_rec=task_rec,
                task_workdir=task_workdir,
                lsp_bin=lsp_bin,
                address_url=address_url,
                model=model,
                boost_thinking=boost_thinking,
                running_only_one_task=log_to_console,
                cli_start=cli_start,
                cli_start_with=cli_start_with,
                chat_id=chat_id,
                run_in_docker=run_in_docker,
                isolation_config=isolation_config,
                experiment=experiment,
                api_key=api_key,
                chat_max_depth=chat_max_depth,
                logger=logger,
            )
        finally:
            if run_in_docker:
                assert image_id is not None, "Image ID should not be None if running in docker"
                try:
                    get_docker_client().remove_container("refact-" + chat_id, force=True)
                except docker.errors.APIError as e:
                    if e.status_code != 404:
                        global_logger.warning("Failed to remove container: {}".format(e))
                if (cache_level <= 0):
                    try:
                        get_docker_client().remove_image(image_id)
                    except Exception as e:
                        global_logger.warning("Failed to remove image (Maybe a different task is using it?): {}".format(e))
                # Clean up docker-compose if needed
                if task_rec.docker_compose_dependencies_yaml is not None:
                    await docker_compose_action(task_dir / task_rec.docker_compose_dependencies_yaml, "down")
    # Handle exceptions and log errors
    except Exception as e:
        logger.error("".join(traceback.format_exception(type(e), e, e.__traceback__)))
        raise

    global_logger.info(f"Finished task {task_rec.make_task_name()}")

async def process_tasks(
    tasks: List[Tuple[Path, Task]],
    workspace_dir: Path,
    lsp_bin: str,
    address_url: str,
    run_in_docker: bool,
    rebuild_image: bool,
    experiment: str,
    api_key: str,

    model: str,
    boost_thinking: bool,
    cli_start: bool,
    cli_start_with: str,
    chat_max_depth: int,

    parallel_jobs: int,
    cache: int,
    ignore_errors: bool,
):
    global_logger.debug(f"Processing {len(tasks)} tasks with {parallel_jobs} parallel jobs")
    global_logger.debug("Remember that you can find logs for each task in their respective directories")
    global_logger.debug(f"Using {model} model, boost_thinking={boost_thinking}")

    semaphore = asyncio.Semaphore(parallel_jobs)
    jobs = []
    stop_event = asyncio.Event()

    async def limited_worker(task_dir, task_rec):
        async with semaphore:
            if stop_event.is_set():
                return "Skipped", None  # Skip if an error occurred before
            try:
                task_result = await run_single_task(
                    task_dir=task_dir,
                    task_rec=task_rec,
                    workspace_dir=workspace_dir,
                    lsp_bin=lsp_bin,
                    address_url=address_url,
                    run_in_docker=run_in_docker,
                    experiment=experiment,
                    api_key=api_key,
                    rebuild_image=rebuild_image,

                    model=model,
                    boost_thinking=boost_thinking,
                    cli_start=cli_start,
                    cli_start_with=cli_start_with,
                    chat_max_depth=chat_max_depth,

                    log_to_console=parallel_jobs == 1,
                    cache_level=cache,
                )
                return "Finished", task_result
            except Exception as e:
                global_logger.error(f"Error in task {task_rec.make_task_name()}: {e}")
                if not ignore_errors:
                    stop_event.set()  # Stop scheduling new tasks
                return "Error", e

    # Create task list
    for task_dir, task_rec in tasks:
        job = asyncio.create_task(limited_worker(task_dir, task_rec))
        jobs.append(job)

    # Wait for the tasks to complete
    results = await asyncio.gather(*jobs, return_exceptions=True)

    finished = []
    errors = []
    unprocessed = []

    for i, (status, result) in enumerate(results):
        if status == "Error":
            errors.append((tasks[i][1].make_task_name(), result))
        elif status == "Skipped":
            unprocessed.append(tasks[i][1].make_task_name())
        elif status == "Finished":
            finished.append(tasks[i][1].make_task_name())

    if len(finished) > 0:
        global_logger.info("Finished {} tasks:\n{}".format(len(finished), "\n".join(finished)))
    if len(unprocessed) > 0:
        global_logger.info("Unprocessed {} tasks:\n{}".format(len(unprocessed), "\n".join(unprocessed)))

    if len(errors) > 0:
        global_logger.error(f"Errors in {len(errors)} tasks:")
        for task_name, error in errors:
            global_logger.error("=============================================================")
            global_logger.error(f"Error in task {task_name}")
            exception = Exception(f"Encountered error during task execution:\n{error}").with_traceback(error.__traceback__)
            global_logger.error("".join(traceback.format_exception(type(exception), exception, exception.__traceback__)))
        global_logger.error("=============================================================")

