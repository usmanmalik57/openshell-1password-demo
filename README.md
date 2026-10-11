# openshell-1password-demo

An AI coding agent fixes a bug and pushes the fix to GitHub, without ever seeing its GitHub token or its OpenAI key.

The agent runs inside an [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) sandbox, and its keys live in a [1Password Environment](https://www.1password.dev/environments). Inside the sandbox, `GITHUB_TOKEN` and `OPENAI_API_KEY` are only placeholders. After you approve, 1Password sends the real keys to the OpenShell gateway for a time you choose. The gateway adds them only where the rules allow: GitHub requests from `git`, with pushes to your repo only, and OpenAI requests from Python.

## What's in the repo

- `pagination.py` has a bug, and `test_pagination.py` shows it. Two of the three tests fail.
- `BUG_REPORT.md` describes the bug. An HTML comment in it hides a prompt injection that asks the agent to send its keys and code to `attacker.example`. If the agent follows it, the gateway blocks the requests, because that host isn't in the rules.
- `agent/` holds bugfix-bot, a small [LangGraph](https://github.com/langchain-ai/langgraph) agent that uses OpenAI's `gpt-5-mini`. It reads the report, fixes the code, runs the tests, and pushes a branch.
- `openshell/` holds the sandbox rules. `github-push.yaml` lets `git` push to one repo, and `openai-python.yaml` lets only Python use the OpenAI key.

## What you need

- Docker and a running OpenShell gateway (tested with OpenShell 0.1.2)
- The 1Password desktop app for Mac or Linux, signed in to a 1Password Business account (a trial works; the OpenShell option may not appear on Individual accounts)
- Your own copy of this repo on GitHub (a fork works)
- A fine-grained GitHub token for your copy only, with **Contents: Read and write**
- An OpenAI API key

## Run it

Run the commands from the repo root.

1. In `openshell/github-push.yaml`, replace `usmanmalik57/openshell-1password-demo` with your copy, such as `your-user/your-repo`. It appears in three paths.

2. Build the agent image and import the two provider profiles. The GitHub profile is NVIDIA's own, and it allows reading only. The push rule from step 1 adds pushing to your one repo.

   ```shell
   docker build -t bugfix-agent:latest agent/
   openshell profile import --url https://raw.githubusercontent.com/NVIDIA/OpenShell/v0.1.2/providers/github.yaml --global
   openshell profile import --file openshell/openai-python.yaml --global
   ```

   If a profile was imported before, OpenShell says it "already exists". That's fine, so skip it.

3. Set up 1Password in the desktop app:
   - Go to **Settings → Developer**, and under **Developer Integrations**, turn on **Provision OpenShell providers**.
   - Go to **Developer → View Environments → New environment**, name it `bugfix-bot`, and add two variables: `GITHUB_TOKEN` and `OPENAI_API_KEY`.
   - In the Environment, under **Connect to**, select **Connect** next to **OpenShell provider**. Choose **Existing profile → GitHub** and the provider name `op-bugfix-bot`.
   - Connect a second time, with **Existing profile → OpenAI** and the provider name `op-bugfix-bot-openai`.
   - For each connection, pick an expiry (1 hour is the shortest) and approve with your account password.

   `openshell provider list` should now show both providers. If you chose other names, change the two `--provider` flags in the next step.

4. Run the agent. The branch must not exist yet in your repo.

   ```shell
   openshell sandbox create --name bugfix-agent --from bugfix-agent:latest \
     --provider op-bugfix-bot --provider op-bugfix-bot-openai \
     --policy openshell/github-push.yaml --no-tty \
     -- /usr/local/agent-venv/bin/python /usr/local/bin/bugfix_agent.py \
        --repo your-user/your-repo --branch bugfix-bot/fix-pagination
   ```

   It first prints `GITHUB_TOKEN is placeholder` and `OPENAI_API_KEY is placeholder`. Then the agent runs the tests (two fail), fixes one line, runs them again (all pass), and pushes the branch. The run takes less than a minute, and your repo then has the new branch with the fix.

5. To see every request the sandbox made, and whether the gateway allowed or denied it, run `openshell logs bugfix-agent`.

To run it again, delete the box first (`openshell sandbox delete bugfix-agent`) and pick a new branch name. When you're done, disconnect the Environment from OpenShell in 1Password, or let the expiry end the access.

## Good to know

- The push rule checks the repo, not the branch, so the agent could also push to `main`. Turn on branch protection for any repo you care about.
- OpenShell identifies programs by their file path, so any Python process in the sandbox can use the OpenAI key. It still can't send the key to any other host.

More details: [1Password's OpenShell docs](https://www.1password.dev/security-for-ai/nvidia-openshell) and [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell).
