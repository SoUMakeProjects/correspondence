"""Azure OpenAI v1 adapter. No provider response text or hidden reasoning is persisted."""

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.agent_contracts import SYSTEM_PROMPT, definitions
from app.model_view import model_view


class ModelError(Exception):
    pass


@dataclass
class ModelChoice:
    name: str
    arguments: str
    usage: dict


class AzureModel:
    source = "live_azure"

    def __init__(self, settings):
        self.settings = settings

    def choose(self, observation, history, timeout):
        context = json.dumps(
            {"observed_data": model_view(observation), "previous_results": history[-12:]}
        )
        if len(context) > self.settings.agent_max_context_characters:
            raise ModelError("context_limit")
        payload = {
            "model": self.settings.azure_openai_deployment,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Process the selected synthetic case using tools. Inspect evidence before acting.",
                },
            ],
            "tools": definitions(),
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "max_completion_tokens": self.settings.agent_max_completion_tokens,
        }
        if observation is not None or history:
            # Context is an actual previous tool result, never a higher-priority instruction.
            payload["messages"].extend(
                [
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "observed_state",
                                "type": "function",
                                "function": {"name": "observe_case", "arguments": "{}"},
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": "observed_state", "content": context},
                ]
            )
        return self.complete(payload, timeout)

    def classify(self, message, timeout):
        from app.custom_intake import CLASSIFY_PROMPT, IntakeClassification

        return self.complete(
            {
                "model": self.settings.azure_openai_deployment,
                "messages": [
                    {"role": "system", "content": CLASSIFY_PROMPT},
                    {"role": "user", "content": json.dumps(message)},
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "classify_mail",
                            "description": "Classify the incoming servicing request.",
                            "strict": True,
                            "parameters": IntakeClassification.model_json_schema(),
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": "classify_mail"}},
                "parallel_tool_calls": False,
                "max_completion_tokens": self.settings.agent_max_completion_tokens,
            },
            timeout,
        )

    def complete(self, payload, timeout):
        if self.settings.azure_openai_reasoning_effort:
            payload = {**payload, "reasoning_effort": self.settings.azure_openai_reasoning_effort}
        request = Request(
            self.settings.azure_openai_base_url + "chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "api-key": self.settings.azure_openai_api_key.get_secret_value(),
            },
            method="POST",
        )
        try:
            with urlopen(
                request, timeout=max(1, min(timeout, self.settings.azure_openai_timeout_seconds))
            ) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ModelError("provider_response_too_large")
                result = json.loads(raw)
        except HTTPError as exc:
            # Do not echo provider messages, URLs, headers, keys or untrusted error codes.
            raise ModelError(f"azure_http_{exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ModelError("azure_connection_or_timeout") from None
        except (ValueError, TypeError):
            raise ModelError("invalid_provider_response") from None
        try:
            choice = result["choices"][0]
            calls = choice["message"].get("tool_calls", [])
            if choice["finish_reason"] != "tool_calls" or len(calls) != 1:
                raise ModelError("one_tool_call_required")
            function = calls[0]["function"]
            name, arguments = function["name"], function["arguments"]
            if (
                not isinstance(name, str)
                or not isinstance(arguments, str)
                or len(arguments) > 16000
            ):
                raise ModelError("invalid_tool_call")
            usage = {
                key: max(0, int(result.get("usage", {}).get(key, 0)))
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
            return ModelChoice(name, arguments, usage)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise ModelError("invalid_provider_response") from None
