from pathlib import Path, PosixPath
import refact
import docker
import time
import subprocess
import tarfile
import os
from datetime import datetime

from refact_scenarios.fakeide_docker import load_docker_config
from refact_scenarios.fakeide_structs import IntegrationDocker
from refact_scenarios.fakeide_logging import global_logger

def compile_static_lsp(opt_level: str) -> None:
    """Compiles the static rust lsp using docker, to be used in isolation.
    It places it where the external lsp expects it"""
    assert refact.__file__ is not None, "refact.__file__ is None, ensure refact is installed"
    global_logger.info("Compiling statically linked lsp to be used for isolation.")

    lsp_dir = Path(refact.__file__).parent.parent.parent
    
    if not (lsp_dir / "Cargo.toml").exists():
        raise Exception(f"Could not find Cargo.toml in {lsp_dir}, ensure refact is installed with `pip install -e python_binding_and_cmdline`")
    
    dockerfile_path = lsp_dir / "docker" / f"lsp-{opt_level}.Dockerfile"
    
    client = docker.from_env()
    start_time = time.time()
    
    build_output = client.api.build(
        path=str(lsp_dir),
        dockerfile=str(dockerfile_path),
        tag="refact-lsp-builder:latest",
        labels={"refact": ""},
        decode=True
    )
    for chunk in build_output:
        if 'error' in chunk:
            global_logger.error(f"Error: {chunk['error']}")
        elif 'stream' in chunk:
            line = chunk['stream'].strip()
            if line.startswith('Step ') or 'error:' in line.lower():
                global_logger.debug(line)

    duration = time.time() - start_time
    global_logger.info(f"Build completed successfully in {duration:.1f} seconds")

    global_logger.info("Creating container to copy lsp to host")
    container = client.containers.create(
        'refact-lsp-builder:latest',
        name='temp-refact-lsp-builder',
        labels={'refact': ''}
    )

    docker_settings = load_docker_config()
    if docker_settings.remote_docker:
        host_home_dir = _get_unix_home_dir(docker_settings.ssh_user)
        dest_path = PosixPath(host_home_dir) / ".cache" / "refact" / "refact-lsp"
    else:
        dest_path = Path.home() / ".cache" / "refact" / "refact-lsp"

    try:
        if docker_settings.remote_docker:
            global_logger.info("Copying lsp to remote host")
            
            mkdir_cmd = _create_ssh_command(docker_settings)
            mkdir_cmd.append(f"mkdir -p '{dest_path.parent}'")
            subprocess.run(mkdir_cmd, check=True)

            cp_cmd = _create_ssh_command(docker_settings)
            cp_cmd.append(f"docker cp temp-refact-lsp-builder:/output/refact-lsp '{dest_path}'")
            subprocess.run(cp_cmd, check=True)
        else:
            global_logger.info("Copying lsp to local machine")
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            bits, _ = container.get_archive('/output/refact-lsp')

            temp_tar = dest_path.parent / 'temp.tar'
            with open(temp_tar, 'wb') as f:
                for chunk in bits:
                    f.write(chunk)

            with tarfile.open(temp_tar) as tar:
                members = [m for m in tar.getmembers() if m.name == 'refact-lsp']
                tar.extractall(path=str(dest_path.parent), members=members)
                
                for member in members:
                    extracted_path = dest_path.parent / member.name
                    current_time = time.time()
                    os.utime(extracted_path, (current_time, current_time))

            temp_tar.unlink()
    except Exception as e:
        global_logger.error(f"Error copying lsp to host: {e}")
    finally:
        global_logger.info("Removing container")
        container.remove()

    global_logger.info("lsp copied to host")

def get_static_lsp_last_modified_time() -> datetime:
    docker_settings = load_docker_config()

    if docker_settings.remote_docker:
        static_lsp_path = PosixPath(_get_unix_home_dir(docker_settings.ssh_user)) / ".cache" / "refact" / "refact-lsp"
        ssh_cmd = _create_ssh_command(docker_settings)
        ssh_cmd.append(f"stat -c %Y '{static_lsp_path}'")

        try:
            result = subprocess.run(ssh_cmd, check=True, capture_output=True, text=True)
            timestamp = float(result.stdout.strip())
            return datetime.fromtimestamp(timestamp)
        except subprocess.CalledProcessError as e:
            raise Exception(f"Could not find static lsp at {static_lsp_path} on remote host") from e
    else:
        static_lsp_path = Path.home() / ".cache" / "refact" / "refact-lsp"
        if not static_lsp_path.exists():
            raise Exception(f"Could not find static lsp at {static_lsp_path}")
        return datetime.fromtimestamp(static_lsp_path.stat().st_mtime)
    
def _create_ssh_command(docker_settings: IntegrationDocker) -> list[str]:
    ssh_cmd = ['ssh']
    if docker_settings.ssh_identity_file is not None:
        ssh_cmd.extend(['-i', docker_settings.ssh_identity_file])
    ssh_cmd.extend(['-p', docker_settings.ssh_port])
    ssh_cmd.append(f"{docker_settings.ssh_user}@{docker_settings.ssh_host}")
    return ssh_cmd

def _get_unix_home_dir(user: str) -> str:
    return f"/home/{user}" if user != 'root' else '/root'
