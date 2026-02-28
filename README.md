# Payslip Email Automator CLI

## CLI Commands (example for February 2026)

### Generate Someone's payslip (February 2026)
```
python3 -m app.cli payslip generate a8462a3c-b84f-4ac6-bc42-b8eb3196a0bb --month 2026-02
```

### Send payslip PDF to employee email
Use the PDF from the generate step (no regeneration):
```
python3 -m app.cli payslip send a8462a3c-b84f-4ac6-bc42-b8eb3196a0bb --month 2026-02 --pdf output/payslips/a8462a3c-b84f-4ac6-bc42-b8eb3196a0bb-2026-02.pdf
```
Or omit `--pdf` to generate and send in one step:
```
python3 -m app.cli payslip send a8462a3c-b84f-4ac6-bc42-b8eb3196a0bb --month 2026-02
```

### Add claims (using the provided invoice images)
```
python3 -m app.cli claim add a8462a3c-b84f-4ac6-bc42-b8eb3196a0bb "AI Tools Allowance - USD 20 (or IDR equivalent)" "cursor invoice.png" --month 2026-02
python3 -m app.cli claim add a8462a3c-b84f-4ac6-bc42-b8eb3196a0bb "Courses Allowance - USD 15 (or IDR equivalent)" "course invoice.png" --month 2026-02
```

### List claims for February 2026
```
python3 -m app.cli claim list a8462a3c-b84f-4ac6-bc42-b8eb3196a0bb --month 2026-02
```
