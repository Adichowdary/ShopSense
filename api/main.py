"""
ShopSense FastAPI Analytics Application.
Provides authoritative, low-latency analytical endpoints across 6 domains:
1. Vendor Analytics
2. Demand Forecasting
3. Customer Intelligence
4. Product Recommendations
5. Advanced Revenue Analytics
6. Marketplace Benchmarking
"""

import os
import time
import django
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ensure Django is initialized when running standalone via Uvicorn
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
try:
    django.setup()
except RuntimeError:
    pass

from api.routers import (
    vendor,
    forecast,
    customers,
    recommendations,
    revenue,
    benchmarking,
)

app = FastAPI(
    title="ShopSense Analytics API",
    description="Production-grade analytical APIs powering the ShopSense E-Commerce Marketplace BI Platform.",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Monitor request execution time for Locust & latency verification."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000  # in ms
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    return response


# Register Analytical API Routers under /api/v1/analytics and /api/analytics
for prefix in ("/api/v1/analytics", "/api/analytics"):
    app.include_router(vendor.router, prefix=prefix)
    app.include_router(forecast.router, prefix=prefix)
    app.include_router(customers.router, prefix=prefix)
    app.include_router(recommendations.router, prefix=prefix)
    app.include_router(revenue.router, prefix=prefix)
    app.include_router(benchmarking.router, prefix=prefix)


@app.get("/api/health", tags=["Health"])
def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "service": "ShopSense FastAPI Analytics Engine",
        "version": "3.0.0",
    }
