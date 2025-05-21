from dataclasses import field
from pathlib import Path
from typing import List, Optional
import yaml

from pydantic import BaseModel, ConfigDict, field_serializer

from refact import chat_client


class Verification(BaseModel):
    run_chat: Optional[List[chat_client.Message]] = None
    run_python: Optional[str] = None
    run_python_workdir: Optional[str] = None
    run_python_params: List[str] = []

class IntegrationDocker(BaseModel):
    label: str
    remote_docker: bool = False
    ssh_host: str = ''
    ssh_port: str = '22'
    ssh_user: str = 'root'
    ssh_identity_file: str = ''

    @classmethod
    def from_dict(cls, dict: dict):
        return cls(**dict)


class IntegrationIsolation(BaseModel):
    docker_image_id: str
    docker_network: Optional[str] = None
    container_workspace_folder: str

    @classmethod
    def from_dict(cls, dict: dict):
        return cls(**dict)


class Task(BaseModel):
    domain: str
    topic: str
    train_or_test: str
    task_name: str

    repo: str
    revision: str

    task: List[chat_client.Message]
    verification: Verification

    repo_also_known_as: Optional[str] = None
    competency_yaml: Optional[str] = None
    dockerfile: Optional[str] = None
    
    integrations_yaml: Optional[str] = None
    variables_yaml: Optional[str] = None
    secrets_yaml: Optional[str] = None
    indexing_yaml: Optional[str] = None
    privacy_yaml: Optional[str] = None

    docker_compose_dependencies_yaml: Optional[str] = None
    working_dir: Path = Path(".")
    ignored_files: List[str] = []

    @field_serializer('working_dir')
    def serialize_working_dir(self, working_dir: Path, _info) -> str:
        return str(working_dir)

    @classmethod
    def from_dict(cls, dict: dict) -> 'Task':
        return cls(**dict)

    def repo_underscores(self):
        repo = self.repo_also_known_as if self.repo_also_known_as else self.repo
        return repo.replace("/", "_").replace("-", "_").replace(".", "_")

    def make_task_name(self):
        repo = self.repo_underscores()
        topic = self.topic.replace("/", "_").replace("-", "_").replace(".", "_")
        train_or_test = self.train_or_test.replace("/", "_").replace("-", "_").replace(".", "_")
        task_name = self.task_name.replace("/", "_").replace("-", "_").replace(".", "_")
        return f"{topic}-{repo}-{train_or_test}-{task_name}"
