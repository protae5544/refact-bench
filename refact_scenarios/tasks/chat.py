import time
import json
import logging

from pathlib import Path
from typing import IO, List, Optional, Set

from refact import chat_client
from refact.lsp_runner import LSPServerRunner
from refact_scenarios.fakeide_logging import global_logger
from refact_scenarios.fakeide_structs import Task
from refact_scenarios.fakeide_utils import query_lsp_version, save_log_json


def swe_verified_guard(messages) -> List[chat_client.Message]:
    mustvebeen_called_once = [
        ["tree", "cat", "search_symbol_definition", "search_symbol_usages", "search_pattern", "search_semantic", "shell"],
        ["debug_script"],
        ["strategic_planning"],
        ["critique"],
    ]
    all_tools_calls = [
        [t.function.name for t in m.tool_calls]
        for m in messages
        if m.tool_calls is not None
    ]
    all_tool_calls_flatten = [t for toll_calls in all_tools_calls for t in toll_calls]
    for stage_i, stage_tools in enumerate(mustvebeen_called_once):
        if not any(t in stage_tools for t in all_tool_calls_flatten):
            stage = stage_i - 1
            break
    else:
        return messages

    last_message_tool_calls = all_tools_calls[-1]
    shell_cnt = sum(1 if t == "shell" else 0 for t in last_message_tool_calls)
    if shell_cnt > 0 and shell_cnt % 5 == 0:
        messages.append(chat_client.Message(
            role="cd_instruction",
            content="💿 Use `debug_script()` instead of `shell()`. Dig deeper than previous attempts, use breakpoints inside the project.",
        ))
    elif ("debug_script" in last_message_tool_calls
          and sum(1 if t == "debug_script" else 0 for t in all_tool_calls_flatten) > 3):
        messages.append(chat_client.Message(
            role="cd_instruction",
            content="💿 You cannot call debug_script more than 3 times.",
        ))
    elif (("update_textdoc" in last_message_tool_calls or "create_textdoc" in last_message_tool_calls)
          and sum(1 if t == "strategic_planning" else 0 for t in all_tool_calls_flatten) == 0
          and sum(1 if t == "debug_script" else 0 for t in all_tool_calls_flatten) > 0):
        messages.append(chat_client.Message(
            role="cd_instruction",
            content="💿 Call strategic_planning() before changing the project.",
        ))
    elif (set([t for tools in all_tools_calls[-20:] for t in tools]) == {"shell", "update_textdoc", "create_textdoc"} \
            or set([t for tools in all_tools_calls[-20:] for t in tools]) == {"shell", "update_textdoc"})\
            and not any([m.content.startswith("💿 If you have difficulties") for m in messages[-20:] if m.content is not None]):
        messages.append(chat_client.Message(
            role="cd_instruction",
            content="💿 If you have difficulties with the correct solution, consider using `debug_script()` or `strategic_planning()`",
        ))
    else:
        for stage_i, stage_tools in enumerate(mustvebeen_called_once[stage + 1:]):
            if any(t in stage_tools for t in last_message_tool_calls):
                messages.append(chat_client.Message(
                    role="cd_instruction",
                    content=f"💿 You cannot call {all_tools_calls[-1]} since you are on the previous step. Please, follow the strategy",
                ))
                break
    return messages


async def chat_loop(
    lsp_runner: LSPServerRunner,
    messages: List[chat_client.Message],
    *,
    model: str,
    chat_id: str,
    chat_remote: bool,
    task_log: IO,
    running_only_one_task: bool,
    temperature: float = 0.4,
    max_steps: int = 50,
    boost_thinking: bool = False,
    domain: str,
) -> List[chat_client.Message]:
    tools = await chat_client.tools_fetch_and_filter(base_url=lsp_runner.base_url(), tools_turn_on=None)
    N = 1
    depth_prev = len(messages)
    for step_n in range(max_steps):
        messages = list(messages)  # a copy
        if boost_thinking:
            max_tokens = 8192  # twice as much to match 4096 non-reasoning tokens token
            stream = False  # streaming is not supported yet in the chat_client with thinking streaming blocks
        else:
            max_tokens = 4096
            stream = True
        choices = await chat_client.ask_using_http(
            base_url=lsp_runner.base_url(),
            messages=messages,
            n_answers=N,
            model_name=model,
            tools=tools,
            verbose=False,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            only_deterministic_messages=False,
            chat_id=chat_id,
            chat_remote=chat_remote,
            boost_thinking=boost_thinking
        )
        messages = choices[0]

        bunch_of_lines = chat_client.print_messages(messages[depth_prev:], also_print_to_console=running_only_one_task)
        task_log.write("\n".join(bunch_of_lines) + "\n")
        task_log.flush()
        depth_prev = len(messages)

        if not messages[-1].tool_calls:
            global_logger.info("CHAT OVER NO TOOL CALLS ANYMORE")
            break
        if domain == 'swe-verified':
            messages = swe_verified_guard(messages)
    else:
        global_logger.warning("CHAT OVER OUT OF TURNS")
    return messages

async def run_chat(
    lsp_runner: LSPServerRunner,
    task_rec: Task,
    task_workdir: Path,
    chat_id: str,
    run_in_docker: bool,
    experiment: str,

    model: str,
    boost_thinking: bool,
    chat_max_depth: int,

    log_to_console: bool,
    logger: logging.Logger,
):
    messages: List[chat_client.Message] = task_rec.task

    (lsp_version, lsp_commit) = await query_lsp_version(lsp_runner)

    task_log = open(task_workdir / "task.log", "w")
    bunch_of_lines = chat_client.print_messages(messages, also_print_to_console=log_to_console)
    task_log.write("\n".join(bunch_of_lines) + "\n")
    task_log.flush()

    started_ts = time.time()
    messages = await chat_loop(
        lsp_runner,
        messages,
        model=model,
        task_log=task_log,
        running_only_one_task=log_to_console,
        chat_id=chat_id,
        temperature=0.0,
        max_steps=chat_max_depth,
        chat_remote=run_in_docker,
        boost_thinking=boost_thinking,
        domain=task_rec.domain
    )
    ended_ts = time.time()

    with open(task_workdir / "passport.json", "w") as f:
        f.write(json.dumps({
            "started_ts": started_ts,
            "ended_ts": ended_ts,
            "orignal_task": task_rec.model_dump(exclude_none=True),
            "experiment": experiment,
            "model": model,
            "lsp_version": lsp_version,
            "lsp_commit": lsp_commit,
            "chat_max_depth": chat_max_depth,
        }, indent=4))

    messages_json = [msg.model_dump(exclude_none=True) for msg in messages]
    save_log_json(task_workdir, "task", messages_json)

    if len(messages) == 0:
        raise RuntimeError("No messages in the chat. Something probably went wrong with LSP, check `refact-lsp.log`.")
