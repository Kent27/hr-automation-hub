from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import claim, employee, payslip
from app.utils.app_logger import setup_app_logger

setup_app_logger()

app = FastAPI(title="HR Automation Hub")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)

app.include_router(employee.router)
app.include_router(claim.router)
app.include_router(payslip.router)


@app.get("/")
def root():
    return {"message": "HR Automation Hub API is running"}
