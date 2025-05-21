import io
import json
import tarfile
import asyncio
import sys
import docker
import logging
import base64
import os

from datetime import datetime
from pathlib import Path
from typing import Optional

from refact import chat_client
from refact.lsp_runner import LSPServerRunner
from refact_scenarios.fakeide_structs import IntegrationIsolation, Task
from refact_scenarios.fakeide_utils import save_log_json
from refact_scenarios.fakeide_logging import global_logger
from refact_scenarios.tasks.docker import get_docker_client
from refact_scenarios.tasks.chat import chat_loop


def extract_logs_from_result(result_json, artifacts_dir):
    """
    Extract logs from a verification result JSON and unpack them into the artifacts directory.
    
    Args:
        result_json: JSON object containing the verification result
        artifacts_dir: Directory where the logs should be unpacked
    """
    if 'logs_tarball_base64' not in result_json:
        return None
    logs_tarball_bytes = base64.b64decode(result_json['logs_tarball_base64'])
    tar_buffer = io.BytesIO(logs_tarball_bytes)
    os.makedirs(artifacts_dir, exist_ok=True)
    with tarfile.open(fileobj=tar_buffer, mode='r:gz') as tar:
        tar.extractall(path=artifacts_dir)
    return os.path.join(artifacts_dir, "logs")


async def run_verification(
    lsp_runner: LSPServerRunner,
    task_rec: Task,
    task_workdir: Path,
    task_dir: Path,
    chat_id: str,
    run_in_docker: bool,
    experiment: str,

    isolation_config: Optional[IntegrationIsolation],

    model: str,
    boost_thinking: bool,
    chat_max_depth: int,

    log_to_console: bool,
    logger: logging.Logger,
):
    if task_rec.verification.run_chat is not None:
        global_logger.info("--------------------- verification using chat -------------------------")
        verify_log = open(task_workdir / "verify.log", "w")
        current_time = datetime.now().strftime("%Y%m%d %H:%M:%S")
        verify_log.write("%s started verification model=%s\n\n" % (current_time, model))
        messages = task_rec.verification.run_chat
        verify_log.write("\n".join(chat_client.print_messages(messages, also_print_to_console=log_to_console)) + "\n")
        verify_log.flush()
        messages = await chat_loop(
            lsp_runner,
            messages,
            model=model,
            task_log=verify_log,
            running_only_one_task=log_to_console,
            temperature=0.0,
            chat_id=chat_id,
            chat_remote=run_in_docker,
            boost_thinking=boost_thinking,
            domain=task_rec.domain
        )
        verify_log.close()
        messages_json = [msg.model_dump(exclude_none=True) for msg in messages]
        save_log_json(task_workdir, "verify", messages_json)
        with open(task_workdir / "result.json", "w") as f:
            f.write(messages[-1].content)

    if task_rec.verification.run_python is not None:
        global_logger.info("--------------------- verification using python -------------------------")
        logger.info("python script: %s", task_rec.verification.run_python)
        if run_in_docker:
            assert isolation_config is not None
            verify_py_workdir = Path(isolation_config.container_workspace_folder)
        else:
            verify_py_workdir = task_workdir / task_rec.repo_underscores()
        if task_rec.verification.run_python_workdir is not None:
            verify_py_workdir = verify_py_workdir / task_rec.verification.run_python_workdir

        path_to_project_verify_py = str(task_workdir / "verify.py")
        script = open(str(task_dir / task_rec.verification.run_python)).read()

        if run_in_docker:
            docker_client = get_docker_client()

            container_name = f"refact-{chat_id}"
            container_script_path = str(verify_py_workdir / "verify.py")

            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                tarinfo = tarfile.TarInfo(name="verify.py")
                tarinfo.size = len(script)
                tar.addfile(tarinfo, io.BytesIO(script.encode()))
            tar_stream.seek(0)
            try:
                logger.info(docker_client.put_archive(container_name, str(verify_py_workdir), tar_stream.getvalue()))
            except docker.errors.APIError as e:
                logger.error(f"Error putting archive to container {container_name}: {e}")
                raise

            logger.info(f"RUN remotely {container_script_path}")
            
            for py_cmd in ["python3", "python"]:
                exec_id = docker_client.exec_create(
                    container_name, 
                    cmd=[py_cmd, container_script_path, *task_rec.verification.run_python_params],
                    workdir=str(verify_py_workdir),
                )["Id"]
                stdout, stderr = docker_client.exec_start(exec_id, demux=True)
                exec_info = docker_client.exec_inspect(exec_id)
                if exec_info["ExitCode"] == 0:
                    break  # success
                else:
                    logger.warning(
                        f"{py_cmd} ran but failed with exit code {exec_info['ExitCode']}, "
                        f"stderr: {(stderr or b'').decode()}"
                    )
        else:
            with open(path_to_project_verify_py, "w") as f:
                f.write(script)

            logger.info("RUN %s", path_to_project_verify_py)
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                path_to_project_verify_py,
                cwd=verify_py_workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

        stdout = stdout.decode() if stdout is not None else ""
        stderr = stderr.decode() if stderr is not None else ""
        if stderr:
            raise RuntimeError(f"Error running verification script: {stderr}")
        
        try:
            result_json = json.loads(stdout)
            artifacts_dir = task_workdir / "artifacts"
            logs_path = extract_logs_from_result(result_json, artifacts_dir)
            if logs_path:
                logger.info(f"Extracted SWE-bench logs to {logs_path}")
                
            # Remove the logs_tarball_base64 field to avoid storing large base64 data
            if 'logs_tarball_base64' in result_json:
                del result_json['logs_tarball_base64']
                # Re-serialize the result without the logs tarball
                stdout = json.dumps(result_json, indent=4)
        except json.JSONDecodeError:
            logger.warning("Failed to parse verification result as JSON, skipping log extraction")
        except Exception as e:
            logger.warning(f"Error extracting logs: {e}")
        
        return stdout
