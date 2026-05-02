"""Basic agent class. See https://mini-swe-agent.com/latest/advanced/control_flow/ for visual explanation
or https://minimal-agent.com for a tutorial on the basic building principles.
"""

import json
import logging
import traceback
from pathlib import Path

from jinja2 import StrictUndefined, Template
from pydantic import BaseModel

from minisweagent import Environment, Model, __version__
from minisweagent.exceptions import InterruptAgentFlow, LimitsExceeded
from minisweagent.utils.serialize import recursive_merge


class AgentConfig(BaseModel):
    """Check the config files in minisweagent/config for example settings."""

    system_template: str
    """Template for the system message (the first message)."""
    system_template_alt: str | None = None
    """Template for the system message (the first message)."""
    instance_template: str
    """Template for the first user message specifying the task (the second message overall)."""
    func_loc1: str | None = None
    """Template for helper function to choose files from list. (Optional)"""
    func_loc2: str | None = None
    """Template for helper function to choose files from list. (Optional)"""
    test_func_loc1: str | None = None
    """Template for helper function to choose test files from list. (Optional)"""
    test_func_loc2: str | None = None
    """Template for helper function to choose test files from list. (Optional)"""
    step_limit: int = 0
    """Maximum number of steps the agent can take."""
    cost_limit: float = 3.0
    """Stop agent after exceeding (!) this cost."""
    output_path: Path | None = None
    """Save the trajectory to this path."""


class DefaultAgent:
    def __init__(self, model: Model, env: Environment, *, config_class: type = AgentConfig, **kwargs):
        """See the `AgentConfig` class for permitted keyword arguments."""
        self.config = config_class(**kwargs)
        self.messages: list[dict] = []
        self.model = model
        self.env = env
        self.extra_template_vars = {}
        self.logger = logging.getLogger("agent")
        self.cost = 0.0
        self.n_calls = 0

    def get_template_vars(self, **kwargs) -> dict:
        return recursive_merge(
            self.config.model_dump(),
            self.env.get_template_vars(),
            self.model.get_template_vars(),
            {"n_model_calls": self.n_calls, "model_cost": self.cost},
            self.extra_template_vars,
            kwargs,
        )

    def _render_template(self, template: str) -> str:
        return Template(template, undefined=StrictUndefined).render(**self.get_template_vars())

    def add_messages(self, *messages: dict) -> list[dict]:
        self.logger.debug(messages)  # set log level to debug to see
        self.messages.extend(messages)
        return list(messages)

    def handle_uncaught_exception(self, e: Exception) -> list[dict]:
        return self.add_messages(
            self.model.format_message(
                role="exit",
                content=str(e),
                extra={
                    "exit_status": type(e).__name__,
                    "submission": "",
                    "exception_str": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
        )

    def run_func_loc1(self, task: str, list_files: list[str]) -> str:
        if not self.config.func_loc1:
            raise ValueError("func_loc1 template is not configured")

        self.extra_template_vars |= {
            "task": task,
            "list_files": "\n".join(list_files),
        }
        self.messages = []
        self.add_messages(
            self.model.format_message(role="system", content=self._render_template(self.config.system_template_alt)),
            self.model.format_message(role="user", content=self._render_template(self.config.func_loc1)),
        )

        try:
            # mini-swe-agent must provide a tool call, so we use an echo command
            message = self.query()

            actions = message.get("extra", {}).get("actions", [])
            if actions:
                raw_echo_command = actions[0].get("command", "") # the list
                return raw_echo_command.replace("echo ", "").strip("'\"") # filter out the "echo" command and slashes

            return message.get("content", "")
        except Exception as e:
            self.logger.error(f"Echo hack failed: {e}")
            return ""
        
    def run_func_loc2(self, task: str, list_file_function: list[str]) -> str:
        if not self.config.func_loc2:
            raise ValueError("test_func_loc1 template is not configured")

        self.extra_template_vars |= {
            "task": task,
            "list_file_function": "\n".join(list_file_function),
        }
        self.messages = []
        self.add_messages(
            self.model.format_message(role="system", content=self._render_template(self.config.system_template_alt)),
            self.model.format_message(role="user", content=self._render_template(self.config.func_loc2)),
        )

        try:
            # mini-swe-agent must provide a tool call, so we use an echo command
            message = self.query()  

            actions = message.get("extra", {}).get("actions", [])
            if actions:
                raw_echo_command = actions[0].get("command", "")
                return raw_echo_command.replace("echo ", "").strip("'\"")

            return message.get("content", "")
        except Exception as e:
            self.logger.error(f"Echo hack failed: {e}")
            return ""

    def run_test_func_loc1(self, task: str, list_files: list[str]) -> str:
        if not self.config.test_func_loc1:
            raise ValueError("test_func_loc1 template is not configured")

        self.extra_template_vars |= {
            "task": task,
            "list_files": "\n".join(list_files),
        }
        self.messages = []
        self.add_messages(
            self.model.format_message(role="system", content=self._render_template(self.config.system_template_alt)),
            self.model.format_message(role="user", content=self._render_template(self.config.test_func_loc1)),
        )

        try:
            message = self.query()

            actions = message.get("extra", {}).get("actions", [])
            if actions:
                raw_echo_command = actions[0].get("command", "")
                return raw_echo_command.replace("echo ", "").strip("'\"")

            return message.get("content", "")
        except Exception as e:
            self.logger.error(f"Echo hack failed: {e}")
            return ""
        
    def run_test_func_loc2(self, task: str, list_file_function: list[str]) -> str:
        if not self.config.test_func_loc2:
            raise ValueError("test_func_loc1 template is not configured")

        self.extra_template_vars |= {
            "task": task,
            "list_file_function": "\n".join(list_file_function),
        }
        self.messages = []
        self.add_messages(
            self.model.format_message(role="system", content=self._render_template(self.config.system_template_alt)),
            self.model.format_message(role="user", content=self._render_template(self.config.test_func_loc2)),
        )

        try:
            message = self.query()

            actions = message.get("extra", {}).get("actions", [])
            if actions:
                raw_echo_command = actions[0].get("command", "")
                return raw_echo_command.replace("echo ", "").strip("'\"")

            return message.get("content", "")
        except Exception as e:
            self.logger.error(f"Echo hack failed: {e}")
            return ""

    def run(self, task: str = "", sigs: str = "", **kwargs) -> dict:
        """Run step() until agent is finished. Returns dictionary with exit_status, submission keys."""
        self.extra_template_vars |= {"task": task, "preprocessed_functions": sigs, **kwargs}
        self.messages = []
        self.add_messages(
            self.model.format_message(role="system", content=self._render_template(self.config.system_template)),
            self.model.format_message(role="user", content=self._render_template(self.config.instance_template)),
        )
        steps = 0
        while True or steps > 250:
            try:
                self.step()
            except InterruptAgentFlow as e:
                self.add_messages(*e.messages)
            except Exception as e:
                self.handle_uncaught_exception(e)
                raise
            finally:
                self.save(self.config.output_path)
            if self.messages[-1].get("role") == "exit":
                break
            steps += 1
        return self.messages[-1].get("extra", {})

    def step(self) -> list[dict]:
        """Query the LM, execute actions."""
        return self.execute_actions(self.query())

    def query(self) -> dict:
        """Query the model and return model messages. Override to add hooks."""
        if 0 < self.config.step_limit <= self.n_calls or 0 < self.config.cost_limit <= self.cost:
            raise LimitsExceeded(
                {
                    "role": "exit",
                    "content": "LimitsExceeded",
                    "extra": {"exit_status": "LimitsExceeded", "submission": ""},
                }
            )
        self.n_calls += 1
        message = self.model.query(self.messages)
        self.cost += message.get("extra", {}).get("cost", 0.0)
        self.add_messages(message)
        return message

    def execute_actions(self, message: dict) -> list[dict]:
        """Execute actions in message, add observation messages, return them."""
        outputs = [self.env.execute(action) for action in message.get("extra", {}).get("actions", [])]
        return self.add_messages(*self.model.format_observation_messages(message, outputs, self.get_template_vars()))

    def serialize(self, *extra_dicts) -> dict:
        """Serialize agent state to a json-compatible nested dictionary for saving."""
        last_message = self.messages[-1] if self.messages else {}
        last_extra = last_message.get("extra", {})
        agent_data = {
            "info": {
                "model_stats": {
                    "instance_cost": self.cost,
                    "api_calls": self.n_calls,
                },
                "config": {
                    "agent": self.config.model_dump(mode="json"),
                    "agent_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                },
                "mini_version": __version__,
                "exit_status": last_extra.get("exit_status", ""),
                "submission": last_extra.get("submission", ""),
            },
            "messages": self.messages,
            "trajectory_format": "mini-swe-agent-1.1",
        }
        return recursive_merge(agent_data, self.model.serialize(), self.env.serialize(), *extra_dicts)

    def save(self, path: Path | None, *extra_dicts) -> dict:
        """Save the trajectory of the agent to a file if path is given. Returns full serialized data.
        You can pass additional dictionaries with extra data to be (recursively) merged into the output data.
        """
        data = self.serialize(*extra_dicts)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2))
        return data
