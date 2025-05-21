import aiohttp
import asyncio
import base64
import inspect
import json
import logging
import os

from pathlib import Path
from functools import wraps
from asgiref.sync import sync_to_async as _sync_to_async
from git import Repo
from refact.lsp_runner import LSPServerRunner

from refact_scenarios.fakeide_structs import Task

def sync_to_async(sync_fn):
    is_gen = inspect.isgeneratorfunction(sync_fn)
    async_fn = _sync_to_async(sync_fn)

    if is_gen:

        @wraps(sync_fn)
        async def wrapper(*args, **kwargs):
            sync_iterable = await async_fn(*args, **kwargs)
            async_iterable = sync_to_async_iterable(sync_iterable)
            async for item in async_iterable:
                yield item

    else:

        @wraps(sync_fn)
        async def wrapper(*args, **kwargs):
            return await async_fn(*args, **kwargs)

    return wrapper

iter_async = sync_to_async(iter)

@sync_to_async
def next_async(it):
    try:
        return next(it)
    except StopIteration:
        raise StopAsyncIteration

async def sync_to_async_iterable(sync_iterable):
    sync_iterator = await iter_async(sync_iterable)
    while True:
        try:
            yield await next_async(sync_iterator)
        except StopAsyncIteration:
            return

def resolve_ssh_short_github_name(repo: str):
    if not repo.startswith("https://") or not repo.startswith("http://"):
        return f'git@github.com:{repo}'
    return repo

def resolve_short_github_name(repo: str):
    if not repo.startswith("https://") or not repo.startswith("http://"):
        return f'https://github.com/{repo}'
    return repo


async def git_clone_to_rev(task_rec: Task, dest_path: Path, logger: logging.Logger):
    if task_rec.repo == "":
        logger.info("No repo specified. Using empty directory.")
        dest_path.mkdir(parents=True, exist_ok=True)
        return
    if dest_path.exists():
        logger.debug(f"{dest_path} resetting to {task_rec.revision}")
        repo = Repo(dest_path)
        await asyncio.get_running_loop().run_in_executor(None, repo.git.reset, '--hard', task_rec.revision)
        await asyncio.get_running_loop().run_in_executor(None, repo.git.clean, '-fdx')
    else:
        logger.info(f"{task_rec.repo} cloning to {dest_path}")
        try:
            repo: Repo = await asyncio.get_running_loop().run_in_executor(None, Repo.clone_from, resolve_ssh_short_github_name(task_rec.repo), dest_path)
        except Exception:
            repo: Repo = await asyncio.get_running_loop().run_in_executor(None, Repo.clone_from,
                                                                          resolve_short_github_name(task_rec.repo),
                                                                          dest_path)
        await asyncio.get_running_loop().run_in_executor(None, repo.head.reset, task_rec.revision, True, True)

async def query_lsp_version(lsp_runner: LSPServerRunner) -> (str, str):
    """
    Get the lsp version and commit hash from the lsp_runner by querying the buildinfo endpoint.

    :param lsp_runner: The lsp_runner object.
    :return: The lsp version and commit hash.
    """

    buildinfo_url = f"{lsp_runner.base_url()[:-3]}/build_info"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10000)) as session:
        async with session.get(buildinfo_url) as response:
            if response.status == 200:
                data = await response.json()
                lsp_version = data["version"]
                lsp_commit = data["commit"]
            else:
                raise RuntimeError(f"cannot fetch {buildinfo_url}\nStatus: {response.status}")

    return lsp_version, lsp_commit

def save_log_json(task_workdir, stepname, messages_json):
    json_path = task_workdir / f"{stepname}.json"
    with open(json_path, "w") as json_file:
        json.dump(messages_json, json_file, indent=4)

    # Iterate through messages_json to find and save base64-encoded images
    image_count = 0
    for message in messages_json:
        if message["role"] == "tool" and isinstance(message["content"], list):
            for content in message["content"]:
                if content["m_type"].startswith("image/"):
                    image_data = content["m_content"]
                    extension = content["m_type"].split("/")[-1]
                    image_path = task_workdir / f"{stepname}_step{image_count:02d}pic.{extension}"
                    with open(image_path, "wb") as image_file:
                        image_file.write(base64.b64decode(image_data))
                    image_count += 1

def get_workspace_dir(args):
    if args.workspace_dir:
        workspace_dir = Path(args.workspace_dir)
    elif "FAKEIDE_WORKSPACE" in os.environ:
        workspace_dir = Path(os.environ["FAKEIDE_WORKSPACE"])
    else:
        workspace_dir = Path.cwd()
        current_path = Path.cwd()
        while current_path != current_path.parent:
            potential_repo = current_path / "fakeide_workspace"
            if potential_repo.exists() and potential_repo.is_dir():
                workspace_dir = potential_repo
                break
            current_path = current_path.parent
    return workspace_dir / f"experiment-{args.experiment}"
