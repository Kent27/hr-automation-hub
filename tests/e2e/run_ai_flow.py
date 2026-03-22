from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4


def _prepare_workspace(repo_root: Path, run_root: Path) -> Dict[str, Path]:
    if run_root.exists():
        shutil.rmtree(run_root)

    data_dir = run_root / "data"
    output_dir = run_root / "output"
    input_dir = run_root / "input"

    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(repo_root / "data" / "employees.json", data_dir / "employees.json")
    (data_dir / "claims.json").write_text("[]\n", encoding="utf-8")
    (data_dir / "holidays_id.json").write_text("{}\n", encoding="utf-8")

    return {
        "run_root": run_root,
        "data_dir": data_dir,
        "output_dir": output_dir,
        "input_dir": input_dir,
    }


def _configure_runtime_env(paths: Dict[str, Path], ollama_base_url: str) -> None:
    os.environ["DATA_DIR"] = str(paths["data_dir"])
    os.environ["OUTPUT_DIR"] = str(paths["output_dir"])
    os.environ["EXTRACTION_ALERT_EMAIL"] = ""
    os.environ["OLLAMA_BASE_URL"] = ollama_base_url


def _default_run_name() -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    unique_suffix = uuid4().hex[:6]
    return f"ai-e2e-{timestamp}-{unique_suffix}"


def _create_holiday_inputs(input_dir: Path) -> Dict[str, Path]:
    from PIL import Image, ImageDraw
    from weasyprint import HTML

    text_pdf = input_dir / "holidays-march-2026-text.pdf"
    scanned_png = input_dir / "holidays-march-scanned.png"
    scanned_pdf = input_dir / "holidays-march-scanned.pdf"

    html = """
    <html><body style="font-family: Arial; font-size: 14px;">
    <h3>Hari Libur Nasional dan Cuti Bersama Maret 2026</h3>
    <p>Hari Libur Nasional</p>
    <p>18 Maret 2026: Hari Suci Nyepi</p>
    <p>20-21 Maret 2026: Idulfitri</p>
    <p>Cuti Bersama</p>
    <p>19 Maret 2026: Cuti Bersama Nyepi</p>
    <p>22-23 Maret 2026: Cuti Bersama Idulfitri</p>
    </body></html>
    """
    HTML(string=html).write_pdf(str(text_pdf))

    image = Image.new("RGB", (1800, 1200), "white")
    draw = ImageDraw.Draw(image)
    lines = [
        "Hari Libur Nasional",
        "18/03/2026 Hari Suci Nyepi",
        "20-21/03/2026 Idulfitri",
        "Cuti Bersama",
        "19/03/2026 Cuti Bersama Nyepi",
        "22-23/03/2026 Cuti Bersama Idulfitri",
    ]
    y = 80
    for line in lines:
        draw.text((80, y), line, fill="black")
        y += 80
    image.save(scanned_png)
    image.save(scanned_pdf, "PDF", resolution=200.0)

    return {
        "text_pdf": text_pdf,
        "scanned_png": scanned_png,
        "scanned_pdf": scanned_pdf,
    }


def run_ai_flow(
    repo_root: Path,
    run_root: Path,
    ollama_base_url: str,
    month: str,
) -> Dict[str, Any]:
    paths = _prepare_workspace(repo_root, run_root)
    _configure_runtime_env(paths, ollama_base_url)

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from app.services.claim_service import claim_service
    from app.services.employee_service import employee_service
    from app.services.holiday_sync_service import holiday_sync_service
    from app.services.ollama_service import ollama_service
    from app.services.payslip_service import payslip_service

    ollama_ping = ollama_service.chat_json(
        prompt='Return JSON only with keys ok=true and run="ai-flow".',
        system_prompt="Strict JSON only.",
        model="qwen3.5:0.8b",
    )

    employee = employee_service.list_employees()[0]

    claim1 = claim_service.add_claim(
        employee_id=employee.id,
        benefit_type="AI Tools Allowance",
        invoice_path=repo_root / "tests" / "assets" / "cursor invoice.png",
        month=month,
    )
    claim2 = claim_service.add_claim(
        employee_id=employee.id,
        benefit_type="Courses Allowance",
        invoice_path=repo_root / "tests" / "assets" / "course invoice.png",
        month=month,
    )

    payslip, payslip_pdf = payslip_service.generate_payslip(employee.id, month)

    holiday_inputs = _create_holiday_inputs(paths["input_dir"])
    text_synced = holiday_sync_service.sync_from_pdf(holiday_inputs["text_pdf"])

    scanned_synced = set()
    if holiday_sync_service.openai_vision_enabled:
        scanned_synced = holiday_sync_service.sync_from_pdf(holiday_inputs["scanned_pdf"])

    claims_json = json.loads((paths["data_dir"] / "claims.json").read_text(encoding="utf-8"))
    holidays_json = json.loads((paths["data_dir"] / "holidays_id.json").read_text(encoding="utf-8"))

    summary = {
        "run_root": str(paths["run_root"]),
        "data_dir": str(paths["data_dir"]),
        "output_dir": str(paths["output_dir"]),
        "input_dir": str(paths["input_dir"]),
        "employee_id": employee.id,
        "month": month,
        "ai_smoke": {
            "ollama_response": ollama_ping,
        },
        "claims": [
            {
                "benefit_type": claim1.benefit_type,
                "amount_raw": claim1.amount_raw,
                "amount_approved": claim1.amount_approved,
                "benefit_limit": claim1.benefit_limit,
                "currency": claim1.currency,
                "fx_rate": (claim1.extraction.raw or {}).get("fx_rate_usd_to_idr")
                if claim1.extraction and claim1.extraction.raw
                else None,
            },
            {
                "benefit_type": claim2.benefit_type,
                "amount_raw": claim2.amount_raw,
                "amount_approved": claim2.amount_approved,
                "benefit_limit": claim2.benefit_limit,
                "currency": claim2.currency,
            },
        ],
        "payslip": {
            "net_pay": payslip.net_pay,
            "pdf_path": str(payslip_pdf),
        },
        "holiday_sync": {
            "text_pdf_synced_count": len(text_synced),
            "scanned_pdf_synced_count": len(scanned_synced),
            "stored_years": sorted(holidays_json.keys()),
        },
        "artifacts": {
            "claims_json": str(paths["data_dir"] / "claims.json"),
            "holidays_json": str(paths["data_dir"] / "holidays_id.json"),
            "payslip_pdf": str(payslip_pdf),
            "text_holiday_pdf": str(holiday_inputs["text_pdf"]),
            "scanned_holiday_pdf": str(holiday_inputs["scanned_pdf"]),
            "claims_count": len(claims_json),
        },
    }

    summary_path = paths["run_root"] / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run end-to-end AI flow in isolated workspace")
    parser.add_argument(
        "--run-root",
        default=None,
        help="Absolute or relative output run root. Defaults to output/ai-e2e-<timestamp>",
    )
    parser.add_argument(
        "--month",
        default="2026-03",
        help="Claim/payslip month in YYYY-MM format",
    )
    parser.add_argument(
        "--ollama-base-url",
        default="http://host.docker.internal:11434",
        help="Ollama base URL reachable from runtime",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    if args.run_root:
        run_root = Path(args.run_root)
        if not run_root.is_absolute():
            run_root = repo_root / run_root
    else:
        run_root = repo_root / "output" / _default_run_name()

    summary = run_ai_flow(
        repo_root=repo_root,
        run_root=run_root,
        ollama_base_url=args.ollama_base_url,
        month=args.month,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
