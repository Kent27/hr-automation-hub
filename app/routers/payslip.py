from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.payslip_models import (
    PayslipGenerateRequest,
    PayslipGenerateResponse,
    PayslipSendResponse,
)
from app.services.payslip_service import payslip_service

router = APIRouter(prefix="/api/payslips", tags=["payslips"])


@router.post("/generate", response_model=PayslipGenerateResponse)
def generate_payslip(payload: PayslipGenerateRequest) -> PayslipGenerateResponse:
    try:
        payslip, pdf_path = payslip_service.generate_payslip(
            payload.employee_id, payload.month, payload.worked_days
        )
        return PayslipGenerateResponse(payslip=payslip, pdf_path=pdf_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/send", response_model=PayslipSendResponse)
def send_payslip(payload: PayslipGenerateRequest) -> PayslipSendResponse:
    try:
        payslip_data, path_sent = payslip_service.send_payslip(
            payload.employee_id,
            payload.month,
            payload.worked_days,
            pdf_path=payload.pdf_path,
        )
        return PayslipSendResponse(
            payslip=payslip_data, pdf_path=path_sent, sent=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{employee_id}/{month}/download")
def download_payslip(employee_id: str, month: str):
    try:
        _, pdf_path = payslip_service.generate_payslip(employee_id, month)
        return FileResponse(pdf_path, media_type="application/pdf")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
