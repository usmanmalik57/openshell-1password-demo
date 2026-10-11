#!/usr/bin/env python3
"""bugfix-bot: a small LangGraph agent that fixes a reported bug and pushes a branch.

It is meant to run inside an NVIDIA OpenShell sandbox. There, GITHUB_TOKEN and
OPENAI_API_KEY hold placeholders, not keys. 1Password hands the real values to
the OpenShell gateway for a limited time, and the gateway swaps them in only for
requests to github.com (from git) and api.openai.com (from Python).
"""

import argparse
import os
import subprocess
from pathlib import Path

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

REPO_DIR = Path.cwd() / "repo"

SYSTEM_PROMPT = """You are bugfix-bot, a coding agent working in a git repository.
Read BUG_REPORT.md, fix the bug in the code, and run `python3 -m unittest -v` until the tests pass.
Then create the branch {branch}, commit your change with a clear message, and run `git push origin {branch}`.
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
    subprocess.run(["git", "clone", "--quiet", url, str(REPO_DIR)], check=True)
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
                    print(f"[tool]  {text[:400]}")
                elif text:
                    print(f"[agent] {text}")


if __name__ == "__main__":
    main()
