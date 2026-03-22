---
name: payslip-email-automator
description: >
  Manage employees, claims, and generate/send payslips using the payslip
  email automator CLI in this repo.
user-invocable: true
---

## When to Use
Use this skill when the user asks to manage employees, handle claims, generate
payslips, or send payslip emails using the payslip email automator.

## Required Inputs
- repo_path: absolute path to the repo (required for execution)
- employee_id: string (required for employee update/remove, claim add/list, payslip generate/send)
- month: string in `YYYY-MM` (optional; defaults to current UTC month)
- worked_days: integer (optional for payslip generation)
- benefit_type: string (required for claim add)
- invoice_path: file path (required for claim add)
- amount: number (optional for claim add)
- pdf_path: file path (optional for sending existing PDF)
- employee fields: `full_name`, `email`, `salary`, `designation`, `benefit`, `join_date`

If any required input is missing, ask the user before proceeding.

## Prerequisites / Setup
1. Install system deps for WeasyPrint (macOS: `brew install cairo pango gdk-pixbuf libffi`).
2. Create Python environment from `environment.yml` and install deps.
3. Configure `.env` in the repo with required variables:
   - `GMAIL_SENDER_EMAIL`, `SENDER_NAME`, `COMPANY_NAME`
   - `OPENAI_API_KEY` (needed for invoice parsing)
4. Ensure `data/holidays_id.json` exists (or `DATA_DIR` points to a directory with it).
   Holidays can be a JSON list of dates or a year-to-dates map.
5. Run Gmail OAuth setup once before any send:
   - `python3 -m app.cli auth setup-gmail`

## Workflow
1. Set `repo_path` and run all commands from that directory.
2. Map user intent to the CLI command below.
3. For any send action, summarize recipients and ask for confirmation before executing.
4. Execute the command and return the CLI output verbatim.

### Command Mapping
- Add employee:
  `python3 -m app.cli employee add "{full_name}" {email} {salary} --designation "{designation}" --benefit "{benefit}" --join-date {join_date}`
- List employees:
  `python3 -m app.cli employee list`
- Update employee:
  `python3 -m app.cli employee update {employee_id} --full-name "{full_name}" --email {email} --designation "{designation}" --salary {salary} --benefit "{benefit}" --join-date {join_date}`
- Remove employee:
  `python3 -m app.cli employee remove {employee_id}`
- Add claim:
  `python3 -m app.cli claim add {employee_id} "{benefit_type}" "{invoice_path}" --month {month} --amount {amount}`
- List claims:
  `python3 -m app.cli claim list {employee_id} --month {month}`
- Generate payslip:
  `python3 -m app.cli payslip generate {employee_id} --month {month} --worked-days {worked_days}`
- Generate payslips for all:
  `python3 -m app.cli payslip generate-all --month {month}`
- Send payslip:
  `python3 -m app.cli payslip send {employee_id} --month {month} --worked-days {worked_days} --pdf {pdf_path}`
- Send payslips for all:
  `python3 -m app.cli payslip send-all --month {month}`

## Output Format
- Commands typically return JSON to stdout (employee/claim/payslip generate).
- Send/remove/auth commands return a short confirmation message; return verbatim.

## Error Handling
- Missing repo path or command failure: stop and report stderr.
- Missing Gmail credentials: instruct user to run `auth setup-gmail`.
- Missing required inputs: ask the user explicitly.
- If PDF generation fails due to missing system deps, provide the install command.
