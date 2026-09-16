# SOCC · лицо машины в командах. Закон M4: каждый шаг = верифицируемый вердикт.
PY ?= python3

.PHONY: help gate test lint secrets pii bootstrap agents dry pult

help:            ## что умеет make
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-12s %s\n",$$1,$$2}'

gate: test secrets pii   ## ГЕЙТ «не с неба»: приёмки + M2 + ПДн (то же, что CI)

test:            ## все 71 сухая приёмка (0₽, stdlib)
	$(PY) ops/run_all_acceptances.py

secrets:         ## закон M2: секретов в GIT нет (сканируются только трекаемые файлы)
	@! git ls-files -z | xargs -0 grep -IE "sk-ant-api[0-9]{2}-|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----" && echo "M2: чисто (в git секретов нет)"

pii:             ## закон ПДн: телефонов клиентов в GIT нет (тестовые заглушки в .py разрешены)
	@! git ls-files -z | grep -zvE "tests?/|_acceptance_|_test\.|probe_" | xargs -0 grep -IE "\+7[0-9]{10}" && echo "ПДн: чисто (в git данных клиентов нет)"

bootstrap:       ## собрать машину с нуля (см. BOOTSTRAP.md)
	$(PY) -m venv .venv && .venv/bin/pip install -e . && .venv/bin/pip install -r requirements-optional.txt && $(MAKE) gate

agents:          ## поставить ритм launchd (macOS, сухой автопилот 3×/сут)
	bash ops/install_agents.sh

dry:             ## сухой ход ЦИКЛ-1 (0₽) — нужен .env и runtime/cycle1/stores.json
	$(PY) scripts/mint/arbiter/ymarket_cycle1_v1.py --store atlas-express-film --dry

pult:            ## ПУЛЬТ: где мы, что горит, lawful_next
	-$(PY) -c "import socc_cli.cli as c; c.main()" home || echo "сначала: pip install -e ."
