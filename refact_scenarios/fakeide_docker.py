import yaml

from pathlib import Path
from typing import Optional

from refact_scenarios.fakeide_structs import IntegrationDocker, IntegrationIsolation


def load_docker_config():
    try:
        global_config_path = Path.home() / ".config" / "refact" / "integrations.d"
        with open(global_config_path / "docker.yaml", 'r') as f:
            docker_yaml = yaml.safe_load(f)
            return IntegrationDocker.from_dict(docker_yaml)
    except yaml.YAMLError as e:
        raise RuntimeError(f"Error reading YAML from {global_config_path / 'docker.yaml'}: {e}")

def load_isolation_config(integrations_yaml_path: Path, variables_yaml_path: Optional[Path]):
    # Load variables from variables.yaml
    variables = {}
    if variables_yaml_path is not None:
        try:
            with open(variables_yaml_path, 'r') as f:
                variables = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise RuntimeError(f"Error reading variables YAML from {variables_yaml_path}: {e}")

    try:
        with open(integrations_yaml_path, 'r') as f:
            integrations_yaml = yaml.safe_load(f)
            # Replace variables for all strings in integrations_yaml
            def replace_string_with_vars(value: str, vars_for_replacements: dict):
                for var, replacement in vars_for_replacements.items():
                    if f"${var}" not in value:
                        continue
                    return replacement.join([replace_string_with_vars(s, vars_for_replacements) for s in value.split(f"${var}")])
                return value
            def replace_with_vars(value, vars_for_replacements: dict):
                if isinstance(value, str):
                    return replace_string_with_vars(value, vars_for_replacements)
                elif isinstance(value, dict):
                    return {key: replace_with_vars(value, vars_for_replacements) for key, value in value.items()}
                elif isinstance(value, list):
                    return [replace_with_vars(v, vars_for_replacements) for v in value]
                else:
                    return value

            integrations_yaml = replace_with_vars(integrations_yaml, variables)
            
            return IntegrationIsolation.from_dict(integrations_yaml["isolation"])
    except yaml.YAMLError as e:
        raise RuntimeError(f"Error reading integrations YAML from {integrations_yaml_path}: {e}")
