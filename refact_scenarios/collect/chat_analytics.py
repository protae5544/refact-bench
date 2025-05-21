import json

from pathlib import Path
from typing import Optional

from .errors import CollectError
from refact_scenarios.fakeide_logging import global_logger

class TokenUsage:
    def __init__(self):
        self.completion_tokens: int = 0
        self.prompt_tokens: int = 0
        self.cache_read_input_tokens: Optional[int] = None
        self.cache_creation_input_tokens: Optional[int] = None

    def total_prompt_tokens(self) -> int:
        return self.prompt_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens

    def legacy_token_str(self):
        return "%s/%s" % (self.total_prompt_tokens(), self.completion_tokens)


class ChatAnalytics:
    """
    Class to store the chat analytics.
    """

    chat_depth: int

    token_usage: TokenUsage

    tool_usage: list[str]

    def __init__(self):
        self.chat_depth = 0
        self.token_usage = TokenUsage()
        self.tool_usage = []


def parse_chat_analytics(chat_file: Path) -> ChatAnalytics:
    """
    Parse the chat analytics from the chat.json file.
    """

    chat_analytics = ChatAnalytics()

    try:
        with open(chat_file, 'r') as f:
            chat = json.load(f)

            assistant_data = [i for i in chat if i["role"] == "assistant"]

            # Token amount information
            usage_data = [i["usage"] for i in assistant_data]
            chat_analytics.token_usage.completion_tokens = sum(
                [i["completion_tokens"] for i in usage_data]
            )
            chat_analytics.token_usage.prompt_tokens = sum(
                [i.get("prompt_tokens", 0) for i in usage_data]
            )
            chat_analytics.token_usage.cache_read_input_tokens = sum(
                [i.get("cache_read_input_tokens", 0) for i in usage_data]
            )
            chat_analytics.token_usage.cache_creation_input_tokens = sum(
                [i.get("cache_creation_input_tokens", 0) for i in usage_data]
            )

            chat_analytics.chat_depth = len(assistant_data)

            for i in assistant_data:
                if "tool_calls" in i:
                    for tool_call in i["tool_calls"]:
                        if tool_call["type"] == "function":
                            chat_analytics.tool_usage.append(tool_call["function"]["name"])
                        else:
                            global_logger.warning("Unknown tool call type: %s" % tool_call["type"])

    except (json.decoder.JSONDecodeError, KeyError, FileNotFoundError) as e:
        raise CollectError("Error parsing chat.json") from e

    return chat_analytics
