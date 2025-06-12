import logging
import sys
import yaml
import os

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from refact import cli_settings
from refact import cli_main
from refact.lsp_runner import LSPServerRunner
from refact_scenarios.fakeide_structs import IntegrationIsolation, Task
from refact_scenarios.fakeide_logging import global_logger
from refact_scenarios.tasks.chat import run_chat
from refact_scenarios.tasks.docker import get_docker_client
from refact_scenarios.tasks.verification import run_verification

def get_lsp_runner(
    task_dir: Path,
    task_rec: Task,
    task_workdir: Path,
    run_in_docker: bool,
    lsp_bin: str,
    api_key: str,
    address_url: str,
):
    args = [
        str(lsp_bin),
    ]
    args.append("--experimental")
    args.append("--ast")
    # args.append("--vecdb")
    args.append("--workspace-folder")
    path_to_project = str(task_workdir / task_rec.repo_underscores() / task_rec.working_dir)
    args.append(path_to_project)
    if task_rec.integrations_yaml is not None:
        args.append("--integrations-yaml")
        hostname = urlparse(address_url).netloc.split(":")[0]
        integrations_yaml = task_dir / task_rec.integrations_yaml
        if run_in_docker and hostname in ["localhost", "0.0.0.0", "127.0.0.1"]:
            integrations = yaml.safe_load(integrations_yaml.read_text())
            # isolation section should be in integrations.yaml!
            if sys.platform.startswith("linux"):
                docker_hostname = "172.17.0.1"
            else:
                # win, mac
                docker_hostname = "host.docker.internal"
            integrations["isolation"]["isolation_address_url"] = address_url.replace(hostname, docker_hostname)
            task_integrations_yaml = task_workdir / "integrations.yaml"
            yaml.dump(integrations, task_integrations_yaml.open("w"))
            args.append(str(task_integrations_yaml))
        else:
            args.append(str(integrations_yaml))
    if task_rec.variables_yaml is not None:
        args.append("--variables-yaml")
        args.append(str(task_dir / task_rec.variables_yaml))
    if task_rec.secrets_yaml is not None:
        args.append("--secrets-yaml")
        args.append(str(task_dir / task_rec.secrets_yaml))
    if task_rec.indexing_yaml is not None:
        args.append("--indexing-yaml")
        args.append(str(task_dir / task_rec.indexing_yaml))
    if task_rec.privacy_yaml is not None:
        args.append("--privacy-yaml")
        args.append(str(task_dir / task_rec.privacy_yaml))
    if api_key:
        args.append("--address-url")
        args.append(address_url)
        args.append("--api-key")
        args.append(api_key)

    refact_lsp_log_path = task_workdir / "refact-lsp.log"

    with open(refact_lsp_log_path, 'w') as log_file:  # this clears the old file
        log_file.write("")

    return LSPServerRunner(
        args,
        verbose=False,
        refact_lsp_log=str(refact_lsp_log_path),
    )


async def run_task_internal(
    task_dir: Path,
    task_rec: Task,
    *,
    task_workdir: Path,
    lsp_bin: str,
    address_url: str,
    model: str,
    boost_thinking: bool,
    running_only_one_task: bool,
    chat_id: str,
    cli_start: bool,
    cli_start_with: str,
    run_in_docker: bool,
    isolation_config: Optional[IntegrationIsolation],
    experiment: str,
    api_key: str,
    chat_max_depth: int,
    logger: logging.Logger,
):
    """
    Start the LSP server
    Run the chat
    Run the verification
    Save the results
    """
    # Start the LSP server
    lsp_runner = get_lsp_runner(
        task_dir=task_dir,
        task_rec=task_rec,
        task_workdir=task_workdir,
        run_in_docker=run_in_docker,
        lsp_bin=lsp_bin,
        api_key=api_key,
        address_url=address_url,
    )
    global_logger.info("Starting LSP server...")
    async with lsp_runner:
        if cli_start:
            caps = await cli_settings.fetch_caps(lsp_runner.base_url())
            cli_settings.cli_yaml = cli_settings.load_cli_or_auto_configure()
            cli_settings.args = cli_settings.CmdlineArgs(
                caps, 
                model=model, 
                path_to_project=str(task_workdir / task_rec.repo_underscores() / task_rec.working_dir), 
                always_pause=True, 
                chat_id=chat_id, 
                chat_remote=run_in_docker
            )
            await cli_main.actual_chat(
                lsp_runner,
                start_with=cli_start_with,
                caps=caps,
            )
            return
        try:
            # Run the chat
            await run_chat(
                lsp_runner=lsp_runner,
                task_rec=task_rec,
                task_workdir=task_workdir,
                chat_id=chat_id,
                run_in_docker=run_in_docker,
                experiment=experiment,
                model=model,
                boost_thinking=boost_thinking,
                chat_max_depth=chat_max_depth,
                log_to_console=running_only_one_task,
                logger=logger,
            )
        finally:
            # Save container LSP's logs
            if run_in_docker:
                container_name = f"refact-{chat_id}"
                container_logs = get_docker_client().logs(
                    container=container_name,
                    stdout=False,
                    stderr=True,
                    timestamps=False,
                )
                with open(task_workdir / "refact-container-lsp.log", "w") as f:
                    f.write(container_logs.decode("utf-8"))

        # Run the verification
        results = await run_verification(
            lsp_runner=lsp_runner,
            task_rec=task_rec,
            task_workdir=task_workdir,
            task_dir=task_dir,
            chat_id=chat_id,
            run_in_docker=run_in_docker,
            experiment=experiment,
            isolation_config=isolation_config,
            model=model,
            boost_thinking=boost_thinking,
            chat_max_depth=chat_max_depth,
            log_to_console=running_only_one_task,
            logger=logger,
        )
        # Save the results
        logger.info(results)
        with open(task_workdir / "result.json", "w") as f:
            f.write(results)

        artifacts_dir = task_workdir / "artifacts"
        if artifacts_dir.exists() and experiment:
            experiment_dir = Path(experiment)
            if experiment_dir.exists():
                task_name = task_rec.make_task_name()
                experiment_artifacts_dir = experiment_dir / task_name / "artifacts"
                os.makedirs(experiment_artifacts_dir.parent, exist_ok=True)
                if experiment_artifacts_dir.exists():
                    import shutil
                    shutil.rmtree(experiment_artifacts_dir)
                try:
                    shutil.copytree(artifacts_dir, experiment_artifacts_dir)
                    logger.info(f"Copied artifacts to {experiment_artifacts_dir}")
                except Exception as e:
                    logger.warning(f"Failed to copy artifacts to experiment directory: {e}")


