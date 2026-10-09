from fastapi import FastAPI

from app.api.bids import router as bids_router
from app.api.simulation import router as simulation_router
from app.api.copilot import router as copilot_router
from app.api.quotes import router as quotes_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="RFQ Quote Management API",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bids_router)
app.include_router(simulation_router)
app.include_router(copilot_router)
app.include_router(quotes_router)