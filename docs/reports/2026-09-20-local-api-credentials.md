# Local API credential lookup verification

Baseline: `c374781` (merged PR #73). The shared server-only resolver supports
OpenAI and JEV aliases from process settings or the ignored `.env.local`, including
the main checkout's file when executing inside a linked worktree. No activation
settings are loaded, no process environment is mutated, and imports do no file I/O.
OpenAI remains limited to the existing instruction-audio generator; no inference
fallback or new provider was added.

Six tests failed before the resolver/client adjustment. Observed verification:

- Windows credential and inference suites: 89 passed.
- Final credential, component and station regression checks: 17 passed.
- Ubuntu credential and client checks: 15 passed, with synthetic keys/mock HTTP.
- Independent read-only review: no blocking findings; test fixture isolation was
  extended to the lowercase legacy alias for case-sensitive platforms.
- Presence-only local check confirmed both configured keys resolve from the main
  checkout's ignored file. Values were not printed, copied or committed.

No live provider call, audio regeneration, component activation or participant
transmission was performed. Existing exact-payload and station gates still apply.
