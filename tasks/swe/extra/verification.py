import subprocess
import json
import sys
import os
import tarfile
import base64
import io
import datetime

# Check if there are any arguments provided
if len(sys.argv) > 3:
    instance_id = sys.argv[1]
    dataset_name = sys.argv[2]
    split_name = sys.argv[3]
else:
    raise Exception("Expected argument with instance-id, dataset-name, and split-name (e.g 'sqlfluff__sqlfluff-1625' 'princeton-nlp/SWE-bench_Lite' 'dev')")

# Reset setup.py, tox.ini, and pyproject.toml files before getting the diff
subprocess.run(
    ["git", "checkout", "--", "setup.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
).stdout.decode()
subprocess.run(
    ["git", "checkout", "--", "tox.ini"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
).stdout.decode()
subprocess.run(
    ["git", "checkout", "--", "pyproject.toml"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
).stdout.decode()


# Get the diff
diff = subprocess.run(
    ["git", "diff"], 
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

if diff.returncode != 0:
    raise Exception("Getting diff failed:\n%s" % diff.stderr.decode())

# This can throw an exception if git diff is not utf-8
diff = diff.stdout.decode()

prediction = {
    "instance_id": instance_id,
    "model_patch": diff,
    "model_name_or_path": "refact",
}

# Create predictions.json
with open("/SWE-bench/predictions.json", "w") as f:
    f.write(
        json.dumps(
            [
                {
                    "instance_id": instance_id,
                    "model_patch": diff,
                    "model_name_or_path": "refact",
                }
            ]
        )
    )

# Run the tests
tests_result = subprocess.run(
    [
        "sh",
        "-c",
        f". .venv/bin/activate && python -m swebench.harness.run_evaluation --dataset_name {dataset_name} --split {split_name} --predictions_path /SWE-bench/predictions.json --max_workers 1 --run_id refact",
    ],
    cwd="/SWE-bench",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Get the return code
return_code = tests_result.returncode

if return_code != 0:
    raise Exception("Running tests failed:\n%s" % tests_result.stderr.decode("utf-8"))

# The run_evaluation will create this based on "--run_id refact"
with open("/SWE-bench/refact.refact.json", "r") as f:
    swe_results = json.load(f)

logs_tarball_base64 = None
logs_dir = "/SWE-bench/logs"
if os.path.exists(logs_dir):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode='w:gz') as tar:
        tar.add(logs_dir, arcname=os.path.basename(logs_dir))
    tar_buffer.seek(0)
    logs_tarball_base64 = base64.b64encode(tar_buffer.read()).decode('utf-8')

result = {}
if swe_results["resolved_instances"] == 1:
    result["worked"] = "YES"
    result["prediction"] = prediction
else:
    result["worked"] = "NO"
    result["problem"] = swe_results
    result["prediction"] = prediction
if logs_tarball_base64:
    result["logs_tarball_base64"] = logs_tarball_base64

print(json.dumps(result, indent=4))
