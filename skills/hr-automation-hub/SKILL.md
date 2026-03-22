---
name: hr-automation-hub
description: Run HR automations including payslip delivery, holiday reminders, employee management, and claims tracking.
metadata: {"openclaw": {"requires": {"bins": ["python3"], "env": ["OPENAI_API_KEY", "GMAIL_SENDER_EMAIL"]}, "primaryEnv": "OPENAI_API_KEY"}}
---

Use this repository to manage employees, track claims, generate payslips, send holiday reminders, and email them via Gmail OAuth.

## Setup

1. Start runtime with Docker:

```bash
docker compose up --build -d
```

2. Ensure env values exist in `.env` (at least `GMAIL_SENDER_EMAIL`, and `OPENAI_API_KEY` for holiday vision fallback).
3. Place Gmail OAuth client secrets at `{baseDir}/credentials/client_secret.json`.
4. Run Gmail OAuth setup once:

```bash
docker compose run --rm hr-automation-hub python -m app.cli auth setup-gmail
```

## Employee management

```bash
docker compose run --rm hr-automation-hub python -m app.cli employee add "Full Name" email@example.com 5500000 \
  --designation "Full Stack Developer" \
  --benefit "AI Tools Allowance:20:USD" \
  --benefit "Courses Allowance:252036:IDR" \
  --join-date 2026-01-19

docker compose run --rm hr-automation-hub python -m app.cli employee list

docker compose run --rm hr-automation-hub python -m app.cli employee update <employee-id> \
  --full-name "Eric Wiyanto" \
  --email wiyantoeric@gmail.com \
  --designation "Full Stack Developer" \
  --salary 5500000 \
  --benefit "AI Tools Allowance:20:USD" \
  --benefit "Courses Allowance:252036:IDR" \
  --join-date 2026-01-19

docker compose run --rm hr-automation-hub python -m app.cli employee remove <employee-id>
```

## Claims

```bash
docker compose run --rm hr-automation-hub python -m app.cli claim add <employee-id> "AI Tools Allowance" "tests/assets/cursor invoice.png" --month 2026-03

docker compose run --rm hr-automation-hub python -m app.cli claim add <employee-id> "Courses Allowance" "tests/assets/course invoice.png" --month 2026-03 --amount 252036

docker compose run --rm hr-automation-hub python -m app.cli claim list <employee-id> --month 2026-03
```

## Payslips

```bash
docker compose run --rm hr-automation-hub python -m app.cli payslip generate <employee-id> --month 2026-03

docker compose run --rm hr-automation-hub python -m app.cli payslip generate <employee-id> --month 2026-03 --worked-days 20

docker compose run --rm hr-automation-hub python -m app.cli payslip generate-all --month 2026-03

docker compose run --rm hr-automation-hub python -m app.cli payslip send <employee-id> --month 2026-03

docker compose run --rm hr-automation-hub python -m app.cli payslip send <employee-id> --month 2026-03 \
  --pdf output/payslips/<employee-id>-2026-03.pdf

docker compose run --rm hr-automation-hub python -m app.cli payslip send-all --month 2026-03
```

## Holiday sync

```bash
docker compose run --rm hr-automation-hub python -m app.cli holiday sync "path/to/official-holiday.pdf"
docker compose run --rm hr-automation-hub python -m app.cli holiday sync-auto --year 2026
docker compose run --rm hr-automation-hub python -m app.cli holiday list 2026
```
