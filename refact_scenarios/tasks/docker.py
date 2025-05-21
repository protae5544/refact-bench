import asyncio
import docker
import logging
import os
import shutil
import yaml

from pathlib import Path

from refact_scenarios.fakeide_logging import global_logger
from refact_scenarios.fakeide_structs import IntegrationDocker, IntegrationIsolation, Task
from refact_scenarios.fakeide_utils import sync_to_async_iterable

def get_docker_client():
    """
    Get the docker client.
    """
    docker_host = os.getenv("DOCKER_HOST")
    if docker_host:
        return docker.APIClient(base_url=docker_host)
    else:
        return docker.APIClient()

def get_docker_config():
    try:
        global_config_path = Path.home() / ".config" / "refact" / "integrations.d"
        with open(global_config_path / "docker.yaml", 'r') as f:
            docker_yaml = yaml.safe_load(f)
            return IntegrationDocker.from_dict(docker_yaml)
    except yaml.YAMLError as e:
        raise RuntimeError(f"Error reading YAML from {global_config_path / 'docker.yaml'}: {e}")

async def build_docker_image_if_needed(
    task_rec: Task,
    repo_path: Path,
    task_dir: Path,
    rebuild_image: bool,
    cache: bool,
    isolation_config: IntegrationIsolation,
    logger: logging.Logger,
) -> str:
    """
    Build the docker image defined in the task record if it does not already exist.
    Return the image ID.

    If the image already exists, return it's image ID.

    The image is built in the task working directory, using the dockerfile
    specified in the task record.
    """
    assert task_rec.dockerfile is not None, "Must specify dockerfile to run task in docker"
    docker_image_tag = isolation_config.docker_image_id

    docker_client = get_docker_client()
    docker_config = get_docker_config()

    if not rebuild_image:
        images = docker_client.images(name=docker_image_tag)
        if len(images) > 0:
            image_id = images[-1]['Id']
            return image_id

    docker_file_path = (task_dir / task_rec.dockerfile).absolute()
    shutil.copy(docker_file_path, repo_path / "Dockerfile")

    global_logger.info(f"Building docker image {docker_image_tag}...")
    generator = docker_client.build(
        path=str(repo_path),
        tag=docker_image_tag,
        labels={"task": task_rec.make_task_name(), docker_config.label: ""},
        forcerm=True,
        decode=True,
        nocache=not cache,
    )
    try:
        async for json_output in sync_to_async_iterable(generator):
            if 'stream' in json_output:
                line = json_output['stream'].strip('\n')
                if len(line) > 0:
                    logger.debug(line)
            else:
                logger.info(f"Json output: {json_output}")
    except Exception as e:
        logger.error("Error parsing output from docker image build: %s" % e)

    logger.info(f"Done building docker image {docker_image_tag}...")
    images = docker_client.images(name=docker_image_tag)
    if len(images) == 0:
        raise RuntimeError(f"Cannot find docker image {docker_image_tag}. Build failed.")

    return images[-1]['Id']

async def docker_compose_action(docker_compose_file: Path, command: str, logger: logging.Logger):
    logger.info(f"Starting docker compose {command}...")
    if command == "up":
        process = await asyncio.create_subprocess_exec(
            'docker', 'compose', '-f', docker_compose_file, 'up', '-d',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    elif command == "down":
        process = await asyncio.create_subprocess_exec(
            'docker', 'compose', '-f', docker_compose_file, 'down',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    else:
        raise RuntimeError(f"{command} is not supported as docker compose action")
    stdout, stderr = await process.communicate()

    if stdout:
        logger.debug("[stdout]\n{}".format('\n'.join(stdout.decode().split('\n')[-5:])))
    if stderr:
        logger.debug("[stderr]\n{}".format('\n'.join(stderr.decode().split('\n')[-5:])))

    logger.info(f"docker compose {command} completed.")
