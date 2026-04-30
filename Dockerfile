FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    git \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Node.js LTS via NodeSource
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# gh CLI — official binary release, not apt
RUN ARCH=$(dpkg --print-architecture) \
    && GH_VERSION=$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest \
        | jq -r '.tag_name' | sed 's/^v//') \
    && curl -fsSL \
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.tar.gz" \
        -o /tmp/gh.tar.gz \
    && tar -xzf /tmp/gh.tar.gz -C /tmp \
    && mv /tmp/gh_${GH_VERSION}_linux_${ARCH}/bin/gh /usr/local/bin/ \
    && rm -rf /tmp/gh*

RUN npm install -g @anthropic-ai/claude-code

RUN pip install --no-cache-dir "python-telegram-bot[webhooks]" httpx pytest

WORKDIR /app

COPY entrypoint.sh ./
COPY scripts/ ./scripts/
COPY bot.py job_manager.py ./

RUN chmod +x entrypoint.sh scripts/*.sh

RUN mkdir -p /workspace

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "bot.py"]
