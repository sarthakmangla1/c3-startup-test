# Iterative C3 fixer

An evidence-driven alternative to `fixers/examples/minimal-llm`. It gathers the case ticket, source, tests, logs, invariants and relevant C3 corpus references; runs public tests and simulator seeds before asking Sonnet 4.6 for a patch; applies only complete file blocks under `src/`; then validates the patch and allows one refinement attempt. If public pytest still fails after refinement, it restores the original source snapshot.

## Test and run

From the repository root:

```sh
python3 -m pytest -q fixers/iterative/test_fix.py
./grade.sh --fixer fixers/iterative --cases practice/A2
docker build --platform linux/amd64 -t c3-fixer-iterative fixers/iterative
./grade.sh --fixer c3-fixer-iterative --cases practice/A2
./grade.sh --fixer c3-fixer-iterative
```

The directory-mode command runs locally (without the Docker sandbox), so grade the built image before submitting. The runtime requires the grader-provided `C3_WORKSPACE`, `C3_CORPUS`, `C3_DEADLINE`, `C3_BUDGET_USD`, `OPENAI_BASE_URL`, and a proxy token. It does not hard-code a repository path or make any edits outside `src/`.

The unit tests check path restrictions and patch-snapshot restoration. These are not a substitute for running every practice case through `grade.sh`.
