# Hosted agent image. Build context = repo root so rules/, policy/, siv/ and
# .agent_configs/ ship with the agent (rule packs are pinned data, not prompts).
FROM python:3.12-slim
WORKDIR /app
COPY agent/requirements.txt agent/requirements.txt
RUN pip install --no-cache-dir -r agent/requirements.txt
COPY siv/ siv/
COPY rules/ rules/
COPY policy/ policy/
COPY .agent_configs/ .agent_configs/
COPY agent/ agent/
EXPOSE 8088
CMD ["python", "agent/main.py"]
