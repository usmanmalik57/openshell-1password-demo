#!/usr/bin/env bash
# run_task.sh: runs bugfix-bot for one task and gives each step only the access it needs.
#
#   ./run_task.sh your-user/your-repo bugfix-bot/fix-pagination
#
# The runner works outside the sandbox, so the agent cannot change its own access:
#   1. Start the sandbox with read-only rules.
#   2. The agent reads the bug report, fixes the bug, runs the tests, and commits.
#   3. The runner checks the commit and runs the tests again. If they fail, nothing is pushed.
#   4. Push is turned on only for the push itself, then turned off again.
#   5. Task complete: both keys expire now, the sandbox is deleted, and both keys are
#      removed from the gateway. The next task needs a new approval in 1Password.
set -uo pipefail

REPO=${1:?usage: ./run_task.sh owner/repo branch}
BRANCH=${2:?usage: ./run_task.sh owner/repo branch}
BOX=${BOX:-bugfix-task}
GITHUB_PROVIDER=${GITHUB_PROVIDER:-op-bugfix-bot}
OPENAI_PROVIDER=${OPENAI_PROVIDER:-op-bugfix-bot-openai}
cd "$(dirname "$0")"

say() { printf '\n\033[1;36m[runner %s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
in_box() { openshell sandbox exec -n "$BOX" --no-tty --timeout 600 -- bash -c "$1"; }
check() { if in_box "cd ~/repo && GIT_TERMINAL_PROMPT=0 $1" >/dev/null 2>&1; then echo "   allowed"; else echo "   blocked"; fi; }

# A GitHub request that always sends the key (the placeholder saved in the clone's remote URL).
key_request() {
  check 'key=$(git remote get-url origin | sed -E "s#https://[^:]+:([^@]+)@.*#\1#"); git -c http.extraHeader="Authorization: Basic $(printf "x-access-token:%s" "$key" | base64 -w0)" ls-remote origin'
}

end_task() {
  say "Task complete: both keys expire now"
  printf '   a request with the key, before:'; key_request
  now=$(date +%s%3N)
  openshell provider update "$GITHUB_PROVIDER" --credential-expires-at "GITHUB_TOKEN=$now" >/dev/null 2>&1
  openshell provider update "$OPENAI_PROVIDER" --credential-expires-at "OPENAI_API_KEY=$now" >/dev/null 2>&1
  for _ in $(seq 30); do in_box '[ -z "${GITHUB_TOKEN:-}" ]' && break; sleep 2; done
  printf '   the same request, after: '; key_request
  say "Delete the sandbox, then remove both keys from the gateway"
  openshell sandbox delete "$BOX" >/dev/null
  for provider in "$GITHUB_PROVIDER" "$OPENAI_PROVIDER"; do
    for _ in $(seq 15); do
      openshell provider delete "$provider" >/dev/null 2>&1 && { echo "   removed $provider"; continue 2; }
      sleep 2
    done
    echo "   could not remove $provider: $(openshell provider delete "$provider" 2>&1 | grep -o "attached to sandbox.*" | head -1)"
  done
}

for provider in "$GITHUB_PROVIDER" "$OPENAI_PROVIDER"; do
  if ! openshell provider get "$provider" >/dev/null 2>&1; then
    echo "Provider $provider not found. Connect the bugfix-bot Environment to OpenShell in 1Password first."
    exit 1
  fi
done

say "Start the sandbox with read-only rules"
openshell sandbox create --name "$BOX" --from bugfix-agent:latest \
  --provider "$GITHUB_PROVIDER" --provider "$OPENAI_PROVIDER" \
  --policy openshell/read-only.yaml --detach >/dev/null || exit 1
for _ in $(seq 60); do
  [ "$(openshell sandbox list 2>/dev/null | awk -v box="$BOX" '$1 == box {print $NF}')" = Ready ] && break
  sleep 1
done

say "The agent works: read the bug report, fix the bug, run the tests, commit"
if ! in_box "/usr/local/agent-venv/bin/python /usr/local/bin/bugfix_agent.py --repo $REPO --branch $BRANCH"; then
  say "The agent failed, so nothing is pushed"; end_task; exit 1
fi

say "The runner checks the work: a new commit on $BRANCH, and the tests again"
if ! in_box "cd ~/repo && [ \"\$(git rev-list --count origin/HEAD..$BRANCH)\" -ge 1 ] && python3 -m unittest -q"; then
  say "The check failed, so nothing is pushed"; end_task; exit 1
fi
printf '   a push before the check passed:'; check "git push origin $BRANCH:refs/heads/$BRANCH-early"

say "Tests pass: turn push on"
openshell policy set "$BOX" --policy openshell/github-push.yaml --wait >/dev/null
opened=$(date +%s)
in_box "cd ~/repo && git push origin $BRANCH"
pushed=$?
openshell policy set "$BOX" --policy openshell/read-only.yaml --wait >/dev/null
closed=$(date +%s)
say "Push is off again (it was on for $((closed - opened)) seconds)"
printf '   another push now:'; check "git push origin $BRANCH:refs/heads/$BRANCH-again"

end_task
[ "$pushed" -eq 0 ] && say "Done: $BRANCH is on GitHub, and the access ended with the task" || exit 1
