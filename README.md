# HR Automation Hub

This project is Docker-first (Conda inside container) and exposes both API + CLI.

## 1) Start the app

```bash
docker compose up --build -d
```

Stop when needed:

```bash
docker compose down
```

## 2) Prepare AI/runtime dependencies

- Pull local Ollama text model:

```bash
ollama pull qwen3.5:0.8b
```

- If Ollama runs on your host while app runs in Docker, set:
  - `OLLAMA_BASE_URL=http://host.docker.internal:11434`

- Holiday sync uses OpenAI vision fallback by default (uses `OPENAI_MODEL`; recommended `gpt-4o` for holiday accuracy).

## 3) Use the CLI prefix

```bash
CLI="docker compose run --rm hr-automation-hub python -m app.cli"
```

All commands below assume `$CLI`.

## 4) Authentication

Run once for Gmail OAuth:

```bash
$CLI auth setup-gmail
```

## 5) Employee commands

Add employee (`--benefit` format: `type:limit` or `type:limit:currency`):

```bash
$CLI employee add "Full Name" email@example.com 5500000 \
  --designation "Full Stack Developer" \
  --benefit "AI Tools Allowance:20:USD" \
  --benefit "Courses Allowance:252036:IDR" \
  --join-date 2026-01-19
```

List/update/remove:

```bash
$CLI employee list
$CLI employee update <employee-id> --full-name "Updated Name" --email updated@example.com --designation "Full Stack Developer" --salary 5500000 --benefit "AI Tools Allowance:20:USD" --benefit "Courses Allowance:252036:IDR" --join-date 2026-01-19
$CLI employee remove <employee-id>
```

## 6) Claim commands

Auto-parse invoice (OCR + local Ollama pipeline):

```bash
$CLI claim add <employee-id> "AI Tools Allowance" "tests/assets/cursor invoice.png" --month 2026-03
```

Manual amount override:

```bash
$CLI claim add <employee-id> "Courses Allowance" "tests/assets/course invoice.png" --month 2026-03 --amount 252036
```

List claims:

```bash
$CLI claim list <employee-id> --month 2026-03
```

## 7) Payslip commands

```bash
$CLI payslip generate <employee-id> --month 2026-03
$CLI payslip generate <employee-id> --month 2026-03 --worked-days 20
$CLI payslip generate-all --month 2026-03
$CLI payslip send <employee-id> --month 2026-03
$CLI payslip send <employee-id> --month 2026-03 --pdf output/payslips/<employee-id>-2026-03.pdf
$CLI payslip send-all --month 2026-03
```

## 8) Holiday commands

Sync from a known PDF path:

```bash
$CLI holiday sync "path/to/official-holiday.pdf"
```

Auto-discover trusted `.go.id` PDF and sync:

```bash
$CLI holiday sync-auto --year 2026
$CLI holiday sync-auto --year 2026 --seed-url "https://www.kemenkopmk.go.id/"
```

List holidays:

```bash
$CLI holiday list
$CLI holiday list 2026
```

## 9) Automation commands

```bash
$CLI automation list
$CLI automation run-due --date 2026-03-31
$CLI automation run holiday-reminder --date 2026-03-31 --force
$CLI automation run payslip-send-all --date 2026-03-31 --force
```

## 10) Run tests

```bash
docker compose run --rm hr-automation-hub python -m pytest /app/tests -q
```
