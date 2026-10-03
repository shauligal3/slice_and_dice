# slice_and_dice

[![CI](https://github.com/shauligal3/slice_and_dice/actions/workflows/ci.yml/badge.svg)](https://github.com/shauligal3/slice_and_dice/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
![Dependencies](https://img.shields.io/badge/runtime%20dependencies-none-brightgreen)

**An interactive command-line shell for slicing, dicing and comparing network performance data.**

`slice_and_dice` was built to answer one question quickly, over billions of
request logs: *where does network acceleration help, where does it hurt, and
why?* Every request is either **accelerated** (`acc`) or **bypassed** (`byp`, the
control group). The shell lets an analyst narrow the data into ever smaller
*scopes*, break a scope down by any dimension, and compare the two traffic
classes side by side. They can then drill into the cohorts that stand out,
down to the timeline of a single request.

```text
[11:datetime > 2024-05-01] in geo = US
[:12 geo = US] Logs: 12.0K
[12:datetime > 2024-05-01 and geo = US] group_by network
network        %gain   %ttfb   %latency  #Acc           #Byp           %share
LTE            12.50   8.00    10.00     900            100            62.50
WiFi           3.00    1.00    2.00      450            50             31.25
3G             -1.00   -2.00   0.50      90             10             6.25
[ 0 - 3 of 3 rows ]
[12:datetime > 2024-05-01 and geo = US] in LTE
[:101 network = LTE] Logs: 1000
[101:datetime > 2024-05-01 and geo = US and network = LTE] samples order-by speed desc
speed size   latency  ttfb   ses
2.5K  40.0K  600      200    1234567891
1.5K  20.0K  900      300    1234567890
```

*(Numbers are illustrative.)*

## Features

- **Scope stack.** `in` narrows the data, `out` steps back, and `out <dimension>`
  removes a condition from the middle of the stack and re-applies the ones inside it.
  Breakdown rows and traffic classes can be stepped into directly by value
  (`in LTE`, `in acc`).
- **Breakdowns.** `group_by` any combination of dimensions, with numeric, date or
  prefix breakpoints. Add aggregate columns (`select median ttfb perc95 speed`),
  sort (`order_by median latency desc`) and page with Enter.
- **Raw data.** Page through sample records with `samples`, or draw each request's
  connection timeline with `timelines` to see where the time went.
- **Policy analytics.** Projection and best-policy reports compare acceleration
  policies within comparable cohorts. They export CSV/JSON results and generate a
  policy-editor script that A/B-tests the recommendations.
- **A real REPL.** Context-aware tab completion driven by a declarative command
  grammar, persistent history, saved scopes, persistent settings, a scriptable
  `-c` mode, and graceful recovery when the server restarts.
- **Zero runtime dependencies.** Pure Python 3 standard library, fully type-annotated
  (`mypy --strict`), linted with ruff, and tested end to end against an in-process
  fake server.

## Installation

```bash
git clone https://github.com/shauligal3/slice_and_dice.git
cd slice_and_dice
python -m pip install .
```

## Usage

```bash
slice-and-dice --host analytics.example.com --port 8080
```

The shell asks for the server password on first use and, after a successful
login, saves it to the settings file (readable only by you). Use
`--no-save-password` to avoid that, or supply the password in the
`SLICE_AND_DICE_PASSWORD` environment variable, which is never saved.

| Option | Meaning |
| --- | --- |
| `--host`, `--port` | Analytics server (default: settings, then `localhost:8080`) |
| `--cid` | Customer id to start with |
| `--no-stack` | Start at the root scope instead of the last 24 hours |
| `--test-mode` | Use the server's test data set |
| `--config-dir` | Where settings, saved scopes and history live (default `~/.config/slice_and_dice`) |
| `--keepalive SECONDS` | Ping interval that keeps the server-side session alive (`0` disables) |
| `-c COMMAND` | Run a command and exit; repeat for several (e.g. `-c 'group_by network'`) |
| `--debug` | Verbose logging and tracebacks |

Inside the shell, `help` lists every command and `help <command>` explains one.

### Commands

| Command | What it does |
| --- | --- |
| `in <dim> [<op>] <value> [and ...]` | Narrow the scope. Operators: `= != > < >= <= ~` or `eq not gt lt gte lte like not-like is-null not-null` |
| `jump_in <conditions>` | Like `in`, evaluated by the server as a single query |
| `out [<dim>]` / `out_all` / `reset` | Step out, drop one condition, go to the root, start over |
| `activity` / `track` | Accelerated vs. bypassed summary; usage and exception counts |
| `group_by <dim> [[breakpoints] <bp> ...] ...` | Break the scope down (flags: `classmerge`, `save_output`) |
| `select` / `unselect` / `order_by` | Add or remove aggregate columns; sort the breakdown |
| `cluster <numeric dim> [<buckets>]` | Suggest breakpoints by clustering values |
| `samples` / `timelines [order-by <dim> [desc]]` | Raw records; per-request event timelines |
| `session <id> [<event>]` | Dump the raw events of one user session |
| `run_report` / `projection_report` | Outcomes per cohort and policy (saved or ad hoc) |
| `find_best_policy` / `build_report` | Best policy per cohort (saved or ad hoc), with policy scripts |
| `recommended_policies`, `training_set` | Policy recommendations; export training data |
| `save_output [<file>]` | Save the last table as CSV |
| `save_scope <name>` / `get_scope <name>` | Bookmark and restore scopes |
| `set <setting> [<value>]` / `save` | Change settings for the session / persist them |
| `show stack\|scope\|sql\|settings\|rest\|selected\|iter\|server` | Inspect internal state |

### Settings

Settings are changed with `set` and persisted with `save`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `max-results` | 10 | Rows per page |
| `use-median` | 1 | Report medians (1) or averages (0) |
| `abbreviate-numbers` | 1 | Show `1.2M` instead of `1234567` |
| `delimiter` / `table-delimiter` | | Column separators (e.g. `\|` for pasting into wikis) |
| `gain-as-msec` | 0 | Show gains as millisecond differences instead of percentages |
| `min-total-samples`, `min-acc-samples`, `min-byp-samples` | 0 | Hide breakdown rows with too few samples |
| `disabled-columns` | | Comma-separated breakdown columns to hide |
| `auto-fetch` | 0 | Run `activity` after every `in` |
| `timeout` | per command | Server request timeout in seconds |
| `api-server-host`, `api-server-port` | `localhost`, 8080 | The analytics server |

## How it works

```text
Shell                     the REPL (cmd.Cmd), assembled from one class per command group
├── ScopeCommands         in, out, jump_in, activity, track, saved scopes
├── BreakdownCommands     group_by, select, order_by, cluster
├── SampleCommands        samples, timelines, session
├── ReportCommands        projection and best-policy reports, training sets, CSV export
├── SettingsCommands      set, save
└── ShellBase             scope stack, prompt, paging, error handling, rendering helpers

CommandGrammar            declarative command grammar: validation + tab completion
ApiClient                 signed HTTP/JSON requests over a kept-alive connection
Report, export            fixed-width tables, CSV and JSON output
Settings, ScopeLibrary    persistent configuration and bookmarks
```

- **The server owns the data.** Each `in` asks it to materialize a subset and
  returns a *scope id*. The client keeps a stack of `(condition, scope id, count)`
  levels, so stepping back is instant. If the server restarts, the stack is
  replayed from the stored conditions.
- **One grammar, two uses.** Structured commands (`select`, `set`, `build_report`)
  are declared as `CommandGrammar` objects. The same state machine validates a
  command before it runs and computes tab completions while it is being typed,
  so the two can never disagree.
- **Authentication.** Every request carries a nonce (the client's Unix time) and
  `sha256("<password>-<nonce>")`, so the password never travels and captured
  requests expire quickly.
- **Command groups.** The shell is assembled from small, single-purpose classes
  sharing a common base, one per file under `src/slice_and_dice/`.

## Development

```bash
python -m pip install -e ".[dev]"
pytest --cov          # unit and end-to-end tests (against an in-process fake server)
ruff check src tests  # lint
ruff format src tests # format
mypy                  # strict type checking
```

CI runs all of the above on Python 3.10 to 3.13.
