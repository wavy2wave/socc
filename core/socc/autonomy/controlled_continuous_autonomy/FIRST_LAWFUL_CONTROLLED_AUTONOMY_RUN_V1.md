
# FIRST LAWFUL CONTROLLED AUTONOMY RUN V1

status: PASS  
current_step: build_first_lawful_controlled_autonomy_run_v1  
lawful_next: validate_first_lawful_controlled_autonomy_run_v1

## Meaning

This is the first explicit controlled autonomy run plan after the controlled continuous autonomy seal.

It is **not** a daemon.  
It is **not** a background loop.  
It is **not** unbounded autonomy.

## Allowed shape

- one explicit bounded controlled run
- current_lawful_next only
- proof-chain required
- idempotent guard required
- operator panel visible
- Codex/Hermes governance active
- must stop after one step
- daemon/background/network remain false
