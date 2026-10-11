# Image for bugfix-bot inside an OpenShell sandbox. OpenShell needs a non-root user.
FROM nvcr.io/nvidia/base/ubuntu:24.04
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates curl python3 python3-venv \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /usr/local/agent-venv \
 && /usr/local/agent-venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
COPY bugfix_agent.py /usr/local/bin/bugfix_agent.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER ubuntu
