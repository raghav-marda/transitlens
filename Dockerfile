FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e ".[dev]"
# Reproduces the whole pipeline: tests, dataset, validation, oracle and random baselines, report.
CMD ["sh", "-c", "pytest -q && transitlens generate --out out --maps 30 --questions 6 --seed 7 && transitlens validate --data out && transitlens evaluate --data out --adapter oracle && transitlens evaluate --data out --adapter random && transitlens report --data out && echo done"]
