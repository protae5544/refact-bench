#!/usr/bin/env python

import json
import os
import pandas as pd
from pathlib import Path
import yaml

# Careful with `%` in the dockerfile template
dockerfile_template = """
REPLACE_HERE

WORKDIR /install
# Install docker cli
# Add Docker's official GPG key:
RUN apt-get update
RUN apt-get install -y ca-certificates curl
RUN install -m 0755 -d /etc/apt/keyrings
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
RUN chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
RUN echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
RUN apt-get update && apt-get install -y docker-ce-cli

# Install required dependencies for SWE-bench (verification)
RUN apt-get install -y -V ca-certificates lsb-release wget
RUN wget https://apache.jfrog.io/artifactory/arrow/$(lsb_release --id --short | tr 'A-Z' 'a-z')/apache-arrow-apt-source-latest-$(lsb_release --codename --short).deb
RUN apt-get update
RUN apt-get install -y -V ./apache-arrow-apt-source-latest-$(lsb_release --codename --short).deb

# Install SWE repo
RUN git clone https://github.com/princeton-nlp/SWE-bench.git /SWE-bench
WORKDIR /SWE-bench
RUN apt-get install -y python3-venv
RUN python3 -m venv .venv
RUN . .venv/bin/activate      && \
    pip install --upgrade pip && \
    pip install . 

WORKDIR /testbed
"""

def dockerfile_from_template(template, task_name):
    content = template.replace("REPLACE_HERE", ("FROM swebench/sweb.eval.x86_64." + task_name.lower().replace("__", "_1776_") + ":latest"))
    return content

def variables_yaml(task_name):
    return {
        "DOCKER_IMAGE_ID": f"{task_name.lower()}:v1",
    }

def generate_subset(df: pd.DataFrame, df_name: str, df_split: str, domain: str, path: Path):
    for _, row in df.iterrows():
        topic = "python"
        train_or_test = "TEST"
        repo = ""
        task_name = row["instance_id"]
        revision = row["base_commit"]

        base_prompt = f"""
            You are solving a Github issue in the repository {repo}.
            You must make the changes to solve, close, or address the issue, directly in the code.
            """

        prompt = base_prompt + row["problem_statement"]

        yaml_config = {
            "domain": domain,
            "topic": topic,
            "train_or_test": train_or_test,
            "repo": repo,
            "task_name": task_name,
            "revision": revision,
            "dockerfile": "./Dockerfile",
            "integrations_yaml": "../../extra/_integrations.yaml",
            "variables_yaml": "./_variables.yaml",
            "verification": {
                "run_python": "../../extra/verification.py",
                "run_python_params": [
                    task_name,
                    df_name,
                    df_split,
                ],
            },
            "task": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        repo = repo.replace("/", "_").replace("-", "_").replace(".", "_")
        topic = topic.replace("/", "_").replace("-", "_").replace(".", "_")
        train_or_test = train_or_test.replace("/", "_").replace("-", "_").replace(".", "_")
        formatted_task_name = task_name.replace("/", "_").replace("-", "_").replace(".", "_")

        task = f"{topic}-{repo}-{train_or_test}-{formatted_task_name}"
        task_yaml = yaml.dump(
            yaml_config,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            indent=4,
            width=120,
        )

        # Create directory task_name and save yaml, dockerfile and variables.yaml
        (path / task_name).mkdir(parents=True, exist_ok=True)
        with open(path / task_name / "Dockerfile", "w") as f:
            f.write(dockerfile_from_template(dockerfile_template, task_name))
        with open(path / task_name / "_variables.yaml", "w") as f:
            f.write(yaml.dump(variables_yaml(task_name), allow_unicode=True))
        with open(path / task_name / f"{task}.yaml", "w") as f:
            f.write(task_yaml)
    return

splits = {'dev': 'data/dev-00000-of-00001.parquet', 'test': 'data/test-00000-of-00001.parquet'}

lite_df = pd.read_parquet("hf://datasets/princeton-nlp/SWE-bench_Lite/" + splits["test"])
lite_dev_df = pd.read_parquet("hf://datasets/princeton-nlp/SWE-bench_Lite/" + splits["dev"])
verified_df = pd.read_parquet("hf://datasets/princeton-nlp/SWE-bench_Verified/" + splits["test"])

generate_subset(lite_df, "princeton-nlp/SWE-bench_Lite", "test", "swe-lite", Path("./lite"))
generate_subset(lite_dev_df, "princeton-nlp/SWE-bench_Lite", "dev", "swe-lite", Path("./lite-dev"))
generate_subset(verified_df, "princeton-nlp/SWE-bench_Verified", "test", "swe-verified", Path("./verified"))
