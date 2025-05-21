import os
import yaml

from pathlib import Path
from pydantic import ValidationError
from typing import List, Optional, Tuple

from refact_scenarios.collect import collect_task_results, CollectError
from refact_scenarios.fakeide_logging import global_logger
from refact_scenarios.fakeide_structs import Task

def task_parse_yaml(task_path: Path) -> Tuple[Path, Task]:
    """
    Parse a task from a yaml file given a it's path.

    Returns a tuple with the task directory and the task record.

    Errors are raised as exceptions.
    """

    # Get task record
    with open(task_path, "r") as file:
        try:
            data = yaml.safe_load(file)
            task_rec = Task.from_dict(dict=data)
        except ValidationError as e:
            errors = []
            for error in e.errors():
                location = " -> ".join(map(str, error["loc"]))
                errors.append(f"{location}: {error['msg']}")
            raise Exception(f"{task_path}:", "\n".join(errors))
        except Exception as e:
            raise Exception(f"Error while parsing task {task_path}: {e}")

    if task_rec.make_task_name() != task_path.stem:
        raise Exception(f"Bad task name: {task_path.stem} != {task_rec.make_task_name()}.yaml")

    task_dir = task_path.parent.resolve()

    return task_dir, task_rec

def task_is_valid(
    task_dir: Path, 
    task_rec: Task,
) -> Tuple[bool, str]:
    """
    Check if the task is valid, and return a message explaining why if it is not.
    """

    if task_rec.verification.run_python:
        if not os.path.exists(str(task_dir / task_rec.verification.run_python)):
            return False, f"Verification script {task_rec.verification.run_python} not found in {task_dir}"

    if task_rec.privacy_yaml:
        if not os.path.exists(str(task_dir / task_rec.privacy_yaml)):
            return False, f"Privacy yaml {task_rec.privacy_yaml} not found in {task_dir}"

    if task_rec.integrations_yaml:
        if not os.path.exists(str(task_dir / task_rec.integrations_yaml)):
            return False, f"Integrations yaml {task_rec.integrations_yaml} not found in {task_dir}"

    if task_rec.indexing_yaml:
        if not os.path.exists(str(task_dir / task_rec.indexing_yaml)):
            return False, f"Indexing yaml {task_rec.indexing_yaml} not found in {task_dir}"

    if task_rec.dockerfile:
        if not os.path.exists(str(task_dir / task_rec.dockerfile)):
            return False, f"Dockerfile {task_rec.dockerfile} not found in {task_dir}"

    return True, ""

def task_should_run(
    task_dir: Path, 
    task_rec: Task,

    workspace_dir: Path,
    experiment: str,
    rerun_all: bool,
) -> Tuple[bool, str]:
    """
    Check if the task should run, and return a message explaining why if it should not.
    """

    if not rerun_all:
        # We don't want to run an already completed task
        try:
            # TODO: make the distinction between a corrupt task and an incomplete one
            collect_task_results(workspace_dir / task_rec.make_task_name(), experiment)
            return False, "Already completed. Use --rerun-all to rerun it anyway."
        except CollectError as e:
            global_logger.debug(f"Error while collecting task results: {e}")

    return True, ""

def get_tasks(
    tasks_path: str,
    workspace_dir: Path,
    experiment: str,
    rerun_all: bool,
    max_task_amount: Optional[int] = 65535, # Default to all tasks
) -> List[Tuple[Path, Task]]:
    if Path(tasks_path).is_dir():
        all_yaml = [f for f in Path(tasks_path).rglob("*.yaml") if not os.path.basename(f).startswith("_")]
    else:
        all_yaml = [Path(tasks_path)]

    tasks = []
    skipped = 0
    for yaml_file in all_yaml:
        task_dir, task_rec = task_parse_yaml(Path(yaml_file))

        is_valid, reason_is_not_valid = task_is_valid(task_dir, task_rec)

        if not is_valid:
            global_logger.error(f"Invalid task {task_rec.make_task_name()}: {reason_is_not_valid}")
            raise Exception(f"Invalid task {task_rec.make_task_name()}: {reason_is_not_valid}")

        should_run, reason_should_not_run = task_should_run(
            task_dir=task_dir,
            task_rec=task_rec,
            workspace_dir=workspace_dir,
            experiment=experiment,
            rerun_all=rerun_all,
        )

        if not should_run:
            global_logger.debug(f"Skipping task {task_rec.make_task_name()}: {reason_should_not_run}")
            skipped += 1
            continue

        tasks.append((task_dir, task_rec))
        if len(tasks) == max_task_amount:
            break

    tasks_pretty = [ task_rec.make_task_name() for _, task_rec in tasks ]
    global_logger.debug("Tasks to run:\n%s", "\n".join(tasks_pretty))

    if skipped > 0:
        global_logger.info(f"Skipped {skipped} tasks.")

    return tasks
