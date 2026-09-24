FROM python:3.13-slim

RUN useradd -m -u 1000 mcp

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY . .

RUN uv sync --no-dev

RUN chown -R mcp:mcp /app && chmod +x entrypoint.sh

# non-root uid 1000, matching ownership of the host bind mount that holds state
USER mcp

EXPOSE 7776
CMD ["./entrypoint.sh"]
