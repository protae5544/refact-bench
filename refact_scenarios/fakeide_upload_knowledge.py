from pathlib import Path

import logging
import yaml
import pandas as pd

from refact import chat_client

async def upload_knowledge_to(host: str, port: int, logger: logging.Logger = logging.getLogger()):
    base_url = f"http://{host}:{port}/v1"
    tasks_path = Path(__file__).parent.parent / "tasks"
    yaml_files1 = tasks_path.glob("*/competency/*.yaml")
    yaml_files2 = tasks_path.glob("*/compressed-trajectories/*.yaml")

    results = []

    for yaml_file in sorted(yaml_files1) + sorted(yaml_files2):
        try:
            with open(yaml_file, 'r') as file:
                data = yaml.safe_load(file)
                topic = data["topic"]

                if competency := data.get("competency", None):
                    call = dict(
                        mem_type="competency",
                        goal=topic,   # searchable
                        project="",
                        payload=competency
                    )

                elif trajectory := data.get("trajectory", None):
                    call = dict(
                        mem_type="trajectory",
                        goal=data["goal"],
                        project="",
                        payload=trajectory
                    )

                response = await chat_client.mem_add(base_url, **call)
                results.append({
                    "file": yaml_file.name,
                    "mem_type": call["mem_type"],
                    "goal": call["goal"],
                    "payload_length": len(call.get("payload", "")),
                    "status": "%r" % response
                })

        except (yaml.YAMLError, FileNotFoundError) as e:
            logger.error(f"Error reading {yaml_file}: {e}")
            results.append({
                "file": str(yaml_file),
                "topic": None,
                "payload_length": 0,
                "status": f"error: {e}"
            })

    df = pd.DataFrame(results)
    logger.info(df)

