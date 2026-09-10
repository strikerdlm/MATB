# Foundation CI harness correction

The omitted-purpose HTTP test now constructs an isolated FastAPI application with
its six concrete router modules, the installed application's exception handlers,
and a copy of its test dependency overrides. Thus the seven real request validators
run under core and auto component selections. No production routes, skips, or
assertions changed. Each request still asserts exactly missing body.execution_purpose.

Commands (cwd webui/backend; executed with async worker support):

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/matb-predictability-testdeps PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 MATB_COMPONENTS=core /root/repos/MATB/.venv/bin/python -B -m pytest -q -p no:cacheprovider -p anyio.pytest_plugin tests/test_purpose_provenance.py -k omitted_purpose_http
```

RED: 5 failed, 2 passed, 27 deselected, 1 warning in 2.77s.
Output /tmp/task2-ci-red.log. The five absent optional routes returned404.

Same command without `-k omitted_purpose_http`:
GREEN core: 34 passed, 1 warning in 5.43s (/tmp/task2-ci-core-green.log).
Same full-module command with MATB_COMPONENTS=auto:
GREEN auto: 34 passed, 1 warning in 4.74s (/tmp/task2-ci-auto-green.log).
Warning: existing python_multipart pending deprecation.

Only the harness test file and this report are included in the fix commit.
Task2 working source remains uncommitted and unrelated.
