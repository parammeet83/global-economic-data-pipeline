# Scheduling with Windows Task Scheduler

The MVP schedules the pipeline with **Windows Task Scheduler running the CLI** (D-31). There is no in-process scheduler (no APScheduler, Airflow or Prefect), so stopping the API can never leave a scheduler running, and overlapping runs are refused by the database (D-19) whichever way a run is started.

## What runs

`scripts/run_pipeline.ps1` runs, from `backend/` with the root `.venv`:

```
python -m src.pipeline.cli run --triggered-by scheduler
```

It appends the CLI output to `logs/pipeline-YYYY-MM-DD.log` (git-ignored; the CLI never prints credentials) and exits with the CLI's exit code, which Task Scheduler shows as **Last Run Result**:

| Exit code | Task Scheduler shows | Meaning |
|---|---|---|
| 0 | `0x0` | success |
| 1 | `0x1` | failed (see the run in the dashboard or the log) |
| 2 | `0x2` | partial success |
| 3 | `0x3` | refused: another run was already in progress |
| 4 | `0x4` | configuration or database startup error; no run row could be created |

Scheduled runs appear in **Pipeline Runs** with trigger **Scheduler**, including failures.

## Prerequisites

1. `backend/.env` is configured and `python -m src.core.config` (from `backend/`) prints "Configuration OK".
2. `alembic upgrade head` has been run.
3. PostgreSQL starts automatically (the `postgresql-x64-17` service is *Automatic* by default).
4. Test the wrapper by hand first, from the repository root:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_pipeline.ps1
   echo $LASTEXITCODE   # 0 on success
   ```

## Create the task

Review `scripts/register_task.ps1` first. It creates a task that runs daily at the given local time, only while you are logged on (so no Windows password is stored), never starts a second instance while one is running, and stops after one hour if something hangs. From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\register_task.ps1 -At 06:00
```

Equivalent manual setup in the Task Scheduler app (*Create Task…*):

- **General:** name `GlobalEconomicDataPipeline`; *Run only when user is logged on*.
- **Triggers:** Daily, 06:00 (times use the Windows time zone; the database stores UTC `TIMESTAMPTZ`).
- **Actions:** Program `powershell.exe`; arguments `-NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\run_pipeline.ps1"`; start in `<repo>`.
- **Settings:** *If the task is already running: Do not start a new instance*; *Stop the task if it runs longer than 1 hour*; *Run task as soon as possible after a scheduled start is missed*.

## Verify, disable, remove

```powershell
Start-ScheduledTask -TaskName GlobalEconomicDataPipeline        # run now
Get-ScheduledTaskInfo -TaskName GlobalEconomicDataPipeline      # LastRunTime, LastTaskResult, NextRunTime
Disable-ScheduledTask -TaskName GlobalEconomicDataPipeline      # pause the schedule
Enable-ScheduledTask -TaskName GlobalEconomicDataPipeline
Unregister-ScheduledTask -TaskName GlobalEconomicDataPipeline -Confirm:$false   # remove it
```

There is no `PIPELINE_SCHEDULE_ENABLED` setting: the schedule is enabled or disabled in Task Scheduler.

## Troubleshooting

- **Last Run Result 0x4** — open the day's log in `logs/`. Usually PostgreSQL was not running or `backend/.env` is missing or invalid.
- **0x3** — a run (CLI, dashboard or a previous scheduled run) was still in progress. If a run crashed, it stays `running` until the next claim after `STALE_RUN_MINUTES` (default 60) marks it `failed` (D-20).
- **0x1 / 0x2** — the run finished; open it in **Pipeline Runs** to see the counts, quality checks and the sanitized error summary.
- **Nothing in the log** — check the task's *Start in* folder and that `.venv\Scripts\python.exe` exists.
