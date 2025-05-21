import argparse
import asyncio
import os

from refact_scenarios.fakeide_static_lsp import compile_static_lsp
from refact_scenarios.fakeide_logging import logger_init
from refact_scenarios.fakeide_utils import get_workspace_dir
from refact_scenarios.collect import collect_table_results
from refact_scenarios.tasks import run_tasks
from refact_scenarios import fakeide_upload_knowledge

async def async_main():
    parser = argparse.ArgumentParser(description="Run scenarios based on YAML configuration.")
    parser.add_argument('-v', '--verbose', help="Verbose output.", action="store_true")

    subparsers = parser.add_subparsers(help="Subcommand help", dest="command")

    # Create the parser for the "run" command
    parser_run = subparsers.add_parser("run", help="Run the scenarios.")

    # Main arguments
    parser_run.add_argument('task', type=str, help="Path to the task yaml or folder with tasks.")
    parser_run.add_argument('--workspace-dir', type=str, help="Specify the workspace directory.")
    parser_run.add_argument('-e', '--experiment', type=str, help="Experiment name.", default="default")
    parser_run.add_argument('--api-key', type=str, help="Specify the API key to pass to the refact-lsp binary", default=os.environ.get("REFACT_API_KEY", ""))

    # This options don't directly affect the results
    parser_run.add_argument('-n', '--amount', type=int, help="Number of tasks to run", default=65535)
    parser_run.add_argument('-j', '--parallel-jobs', type=int, help="Number of parallel jobs to run", default=1)
    parser_run.add_argument('--docker', help="Run task in docker", action="store_true")
    parser_run.add_argument('--rebuild-image', help="Rebuild the docker image", action="store_true")
    parser_run.add_argument('--rerun-all', help="Task will be run even if the output directory already exists", action="store_true")
    parser_run.add_argument('--address-url', type=str, help="Specify the inference address to the refact-lsp binary.", default="Refact")
    parser_run.add_argument('--cache-level', type=int, help="Sets how much are docker-related artifacts going to persist after the run.\n1 or higher caches image build artifacts.\n2 or higher also caches the full image.", default=2)
    parser_run.add_argument('--ignore-errors', help="Ignore errors in the task", action="store_true")

    # Control some parameters that we want to try out for the same task
    parser_run.add_argument('-m', '--model', type=str, help="Specify the model to use")
    parser_run.add_argument('--boost-thinking', help="Whether to use reasoning while evaluation", action="store_true")
    parser_run.add_argument('--chat-max-depth', type=int, help="Maximum depth of chat", default=30)

    # Debugging options
    parser_run.add_argument('--cli', help="Prepare the environment and run CLI", action="store_true")
    parser_run.add_argument('--cli-start-with', type=str, help="Load trajectory into CLI")

    # Create the parser for the "collect" command
    parser_collect = subparsers.add_parser('collect', help="Collect results for the table.")
    parser_collect.add_argument('--workspace-dir', type=str, help="Specify the workspace directory.")
    parser_collect.add_argument("--experiment", type=str, help="Experiment name.", default="default")

    # Create the parser for the "compile-static-lsp" command
    parser_compile_static_lsp = subparsers.add_parser('compile-static-lsp', help="Compile the statically linked lsp to be used for isolation.")
    parser_compile_static_lsp.add_argument('opt_level', type=str, help="Optimization level for the static lsp. Can be 'debug' or 'release'.", choices=["debug", "release"])

    # Create the parser for the "upload-knowledge" command
    parser_upload_knowledge = subparsers.add_parser('upload-knowledge', help="Upload knowledge to refact-lsp.")
    parser_upload_knowledge.add_argument('port', type=int, help="Port to connect to refact-lsp.")

    # Finally, parse the arguments
    args = parser.parse_args()

    logger_init(args.verbose)

    match args.command:
        case "run":
            return await run_tasks(args)
        case "collect":
            collect_table_results(get_workspace_dir(args), args.experiment, True)
            return 0
        case "compile-static-lsp":
            compile_static_lsp(args.opt_level)
            return 0
        case "upload-knowledge":
            await fakeide_upload_knowledge.upload_knowledge_to("127.0.0.1", int(args.port))
            return 0
        case _:
            parser.print_help()
            return 1

def main():
    # Entry point for command line
    return asyncio.run(async_main())


if __name__ == "__main__":
    exit(main())
