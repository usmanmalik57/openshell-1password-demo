#!/usr/bin/env python3
"""bugfix-bot: a small LangGraph agent that fixes a reported bug and commits the fix.

It is meant to run inside an NVIDIA OpenShell sandbox, started by run_task.sh. There,
GITHUB_TOKEN and OPENAI_API_KEY hold placeholders, not keys. 1Password hands the real
values to the OpenShell gateway, and the gateway swaps them in only for requests that
the current rules allow. The agent has no push access: run_task.sh checks the commit
and pushes it.
"""

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

REPO_DIR = Path.home() / "repo"

SYSTEM_PROMPT = """You are bugfix-bot, a coding agent working in a git repository.
Read BUG_REPORT.md, fix the bug in the code, and run `python3 -m unittest -v` until the tests pass.
Then create the branch {branch} and commit your change with a clear message.
Do not push: you have no push access, and a runner outside the sandbox checks your commit and pushes it.
Finish with a two-sentence summary of what you changed."""


@tool
def run_shell(command: str) -> str:
    """Run a shell command in the repository and return its exit code and output."""
    result = subprocess.run(
        command, shell=True, cwd=REPO_DIR, capture_output=True, text=True, timeout=120
    )
    return f"exit code {result.returncode}\n{result.stdout}{result.stderr}"[-4000:]


@tool
def read_file(path: str) -> str:
    """Return the contents of a text file in the repository."""
    return (REPO_DIR / path).read_text()


@tool
def write_file(path: str, content: str) -> str:
    """Replace the contents of a file in the repository."""
    (REPO_DIR / path).write_text(content)
    return f"wrote {len(content)} characters to {path}"


TOOLS = [run_shell, read_file, write_file]


def build_agent(model: str):
    llm = ChatOpenAI(model=model).bind_tools(TOOLS)

    def call_model(state: MessagesState):
        return {"messages": [llm.invoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile()


def describe(name: str) -> str:
    """Say whether an environment variable holds an OpenShell placeholder, without printing it."""
    value = os.environ.get(name, "")
    if not value:
        return "not set"
    return "placeholder" if value.startswith("openshell:resolve:") else "a REAL value (not sandboxed!)"


def clone(repo: str) -> None:
    token = os.environ["GITHUB_TOKEN"]  # a placeholder inside the sandbox
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    # OpenShell reloads the sandbox's rules a few seconds after it starts, which can cut
    # a connection that is open at that moment, so try the clone a few times.
    for _ in range(3):
        if subprocess.run(["git", "clone", "--quiet", url, str(REPO_DIR)]).returncode == 0:
            break
        shutil.rmtree(REPO_DIR, ignore_errors=True)
        time.sleep(5)
    else:
        raise SystemExit(f"could not clone {repo}")
    for key, value in (("user.name", "bugfix-bot"), ("user.email", "bugfix-bot@example.com")):
        subprocess.run(["git", "config", key, value], cwd=REPO_DIR, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True, help="GitHub repository as owner/name")
    parser.add_argument("--branch", default="bugfix-bot/fix")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5-mini"))
    args = parser.parse_args()

    print(f"[setup] GITHUB_TOKEN is {describe('GITHUB_TOKEN')}")
    print(f"[setup] OPENAI_API_KEY is {describe('OPENAI_API_KEY')}")
    clone(args.repo)
    print(f"[setup] cloned {args.repo}")

    agent = build_agent(args.model)
    messages = [
        ("system", SYSTEM_PROMPT.format(branch=args.branch)),
        ("user", f"Fix the bug reported in BUG_REPORT.md in {args.repo}."),
    ]
    config = {"recursion_limit": 40}
    for update in agent.stream({"messages": messages}, config, stream_mode="updates"):
        for node, data in update.items():
            for message in data["messages"]:
                for call in getattr(message, "tool_calls", None) or []:
                    print(f"[agent] {call['name']}({str(call['args'])[:300]})")
                text = message.content if isinstance(message.content, str) else str(message.content)
                if node == "tools":
                    lines = [line for line in text.splitlines() if line.strip()] or [""]
                    shown = lines[0] if len(lines) == 1 else f"{lines[0]} … {lines[-1]}"
                    print(f"[tool]  {shown[:160]}")
                elif text:
                    print(f"[agent] {text}")


if __name__ == "__main__":
    main()
