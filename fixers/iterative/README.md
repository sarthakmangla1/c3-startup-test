# Iterative C3 fixer

An evidence-driven alternative to `fixers/examples/minimal-llm`. It gathers the case ticket, source, tests, logs, invariants and relevant C3 corpus references; runs public tests and simulator seeds before asking Sonnet 4.6 for a patch; applies only complete file blocks under `src/`; then validates the patch and allows one refinement attempt. If public pytest still fails after refinement, it restores the original source snapshot.

## Test and run

From the repository root:

```sh
python3 -m pip install pytest pyyaml
python3 -m py_compile fixers/iterative/fix.py fixers/iterative/test_fix.py
python3 -m pytest -q fixers/iterative/test_fix.py

# Optional directory mode requires an executable run.sh after checkout:
chmod +x fixers/iterative/run.sh
# Use the same venv for the local fixer process, not only for grade.sh
PATH="$PWD/grader/.venv/bin:$PATH" ./grade.sh --fixer fixers/iterative --cases practice/A2

# Recommended: grade the actual Docker image you'll submit
docker build --platform linux/amd64 -t c3-fixer-iterative fixers/iterative
./grade.sh --fixer c3-fixer-iterative --cases practice/A2
./grade.sh --fixer c3-fixer-iterative
```

The runtime requires grader-provided `C3_WORKSPACE`, `C3_CORPUS`, `C3_DEADLINE`, `C3_BUDGET_USD`, `OPENAI_BASE_URL`, and a proxy token. It does not hard-code a repository path or make edits outside `src/`.

The unit tests check patch parsing, source-path restrictions, snapshot restoration and corpus-term extraction. They are not a substitute for running every practice case through `grade.sh`.
