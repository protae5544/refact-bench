# Refact-Bench

## Introduction

Refact-Bench is a benchmarking tool designed to evaluate AI models on software engineering tasks using the SWE-Bench framework. It provides a standardized environment for testing model performance on real-world programming challenges extracted from GitHub issues.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Running Tasks](#running-tasks)
  - [Local Inference](#local-inference)
  - [Preparing SWE-Bench Tasks](#preparing-swe-bench-tasks)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before installing Refact-Bench, ensure you have the following:

- Python 3.7 or higher
- Docker installed and running
- Git
- pip package manager

## Installation

### 1. Install Python Dependencies

First, install the required Python packages:

```sh
pip install -e .
```

This will install all dependencies listed in `setup.py`, including the `refact` package.

### 2. Prepare the Static LSP Binary

Clone the Refact repository and build the necessary components. To reproduce SWE evaluation results, you need to use following branches of `refact`:
- https://github.com/smallcloudai/refact/tree/swe-boosted-prompt for SWE-lite
- https://github.com/smallcloudai/refact/tree/swe-boosted-prompt-verified for SWE-verified


```sh
git clone https://github.com/smallcloudai/refact.git
pip install -e ./refact/refact-agent/engine/python_binding_and_cmdline
fakeide compile-static-lsp release
```

This step compiles the Language Server Protocol (LSP) implementation needed for code analysis.

### 3. Build Native LSP Binary

```sh
cd ./refact/refact-agent/engine/
cargo build --release
mkdir -p ./python_binding_and_cmdline/refact/bin/
cp ./target/release/refact-lsp ./python_binding_and_cmdline/refact/bin/refact-lsp
```

This builds the Rust-based LSP binary and places it in the correct location for the Python package to use.

## Configuration

### Set Up Docker Integration

Create a Docker integration configuration file:

```sh
mkdir -p ~/.config/refact/integrations.d/
```

Then set up the Docker integration configuration (this will **overwrite** any existing Docker integration config):

```sh
cat > ~/.config/refact/integrations.d/docker.yaml << 'EOF'
label: ref
docker_daemon_address: ''
docker_cli_path: docker
remote_docker: false
ssh_host: ''
ssh_user: root
ssh_port: '22'
ssh_identity_file: ''
available:
  on_your_laptop: true
  when_isolated: true
confirmation:
  ask_user: []
  deny: []
EOF
```

This configuration allows Refact-Bench to use Docker for creating isolated environments for each benchmark task.

## Usage

### Running Tasks

To run a benchmark task, use the `fakeide run` command. For example, to run the `swe-verified` tasks using the `claude-3-7-sonnet` model:

```sh
fakeide run --api-key <API-KEY> --model claude-3-7-sonnet --docker tasks/swe/verified --experiment my-experiment
```

Replace `<API-KEY>` with Refact key and `my-experiment` with a name to group your benchmark runs.

To collect the results after running tasks:

```sh
fakeide collect --experiment my-experiment
```

The results of the benchmark will be stored in `./results/`

### Local Inference

If you want to test models on your self-hosted server, specify the `--address-url` parameter with your local address:

```sh
fakeide run --address-url http://localhost:8080 --api-key <API-KEY> --model claude-3-7-sonnet --docker tasks/swe/verified
```

Note: Your server should be started on `0.0.0.0`. A common use case with node is:
```sh
ssh <node-name> -L 0.0.0.0:8008:0.0.0.0:8008
```

### Preparing SWE-Bench Tasks

The `translation.py` script in the `tasks/swe` directory is used to prepare SWE-Bench tasks for evaluation. It converts SWE-Bench datasets into the format required by Refact-Bench:

```sh
cd tasks/swe
python translation.py
```

This script processes the SWE-Bench datasets (Lite, Lite-dev, and Verified) and generates the necessary task files in the respective directories.

## Project Structure

The main components of Refact-Bench are:

- `refact_scenarios/`: Core Python package with the implementation of the benchmarking framework
- `tasks/`: Contains the benchmark tasks
  - `swe/`: SWE-Bench related tasks
    - `verified/`: Verified SWE-Bench tasks
    - `lite/`: SWE-Bench Lite tasks
    - `lite-dev/`: Development subset of SWE-Bench Lite
    - `translation.py`: Script to prepare SWE-Bench tasks
- `fakeide-logs/`: Contains logs from benchmark runs

## Troubleshooting

check the logs in the `fakeide-logs/` directory.
