# openshell-1password-demo

An AI coding agent fixes a bug and the fix is pushed to GitHub, without the agent ever seeing its GitHub token or its OpenAI key. Each step of the task gets only the access it needs, and the access ends when the task is done.

The agent runs inside an [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) sandbox, and its keys live in a [1Password Environment](https://www.1password.dev/environments). Inside the sandbox, `GITHUB_TOKEN` and `OPENAI_API_KEY` are only placeholders. After you approve, 1Password sends the real keys to the OpenShell gateway for a time you choose. The gateway adds them only where the rules allow: GitHub requests from `git` and OpenAI requests from Python.

A runner script, `run_task.sh`, works outside the sandbox and changes those rules step by step. The agent works with read-only access. Push is turned on only after the tests pass, and only for the push itself. When the task is done, the runner expires both keys and removes them from the gateway.

## What's in the repo

- `pagination.py` has a bug, and `test_pagination.py` shows it. Two of the three tests fail.
- `BUG_REPORT.md` describes the bug. An HTML comment in it hides a prompt injection that asks the agent to send its keys and code to `attacker.example`. If the agent follows it, the gateway blocks the requests, because that host isn't in the rules.
- `agent/` holds bugfix-bot, a small [LangGraph](https://github.com/langchain-ai/langgraph) agent that uses OpenAI's `gpt-5-mini`. It reads the report, fixes the code, runs the tests, and commits the fix to a branch. It has no push access.
- `run_task.sh` is the runner. It starts the sandbox, runs the agent, checks the work, pushes it, and ends the access.
- `openshell/` holds the sandbox rules. `read-only.yaml` is used while the agent works, `github-push.yaml` adds pushing to one repo, and `openai-python.yaml` lets only Python use the OpenAI key.

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
   - For each connection, pick an expiry and approve with your account password.

   `openshell provider list` should now show both providers. If you chose other names, set them with `GITHUB_PROVIDER=… OPENAI_PROVIDER=…` in front of the command in the next step.

4. Run the task. The branch must not exist yet in your repo.

   ```shell
   ./run_task.sh your-user/your-repo bugfix-bot/fix-pagination
   ```

   The runner prints each step:
   - It starts the sandbox with read-only rules.
   - The agent reads the report, runs the tests (two fail), fixes one line, runs them again (all pass), and commits. Both keys show as `placeholder`.
   - The runner runs the tests again and shows that a push is still blocked.
   - It turns push on, pushes the branch, turns push off again, and shows that another push is blocked.
   - It expires both keys and shows a request with the GitHub key going from allowed to blocked. Then it deletes the sandbox and removes both keys from the gateway.

   Your repo then has the new branch with the fix.

Because the runner removes the keys at the end, every run needs a new approval: connect the Environment again in 1Password (step 3), and pick a new branch name.

## Good to know

- The runner decides when the task starts and ends, and it controls the gateway, so run it from your own machine, outside the sandbox.
- The push rule checks the repo, not the branch, so a push could also go to `main`. Turn on branch protection for any repo you care about.
- OpenShell identifies programs by their file path, so any Python process in the sandbox can use the OpenAI key. It still can't send the key to any other host.

More details: [1Password's OpenShell docs](https://www.1password.dev/security-for-ai/nvidia-openshell) and [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell).
