import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.demo import router as demo_router
from app.api.alerts import router as alerts_router
from app.api.checkout import router as checkout_router
from app.api.mercado_pago import router as mercado_pago_router
from app.api.conversations import router as conversations_router
from app.api.whatsapp import router as whatsapp_router
from app.api.whatsapp_settings import router as whatsapp_settings_router

from app.api.businesses import router as businesses_router
from app.api.auth import router as auth_router
from app.api.employees import router as employees_router
from app.api.products import router as products_router
from app.api.orders import router as orders_router


app = FastAPI(
    title="AI Customer Assistant API"
)


@app.middleware("http")
async def demo_deployment_boundary(request: Request, call_next):
    if os.getenv("DEMO_ONLY", "false").lower() == "true":
        path = request.url.path
        public = (request.method == "GET" and (path.startswith("/panel/") or path in {"/panel", "/demo/config", "/", "/docs", "/openapi.json", "/docs/oauth2-redirect"})) or (request.method == "POST" and path == "/demo/session")
        if not public:
            from app.services.demo_access import check_demo_route
            from fastapi import HTTPException
            try:
                check_demo_route(request.method, path)
            except HTTPException as error:
                return JSONResponse({"detail": error.detail}, status_code=error.status_code)
    response = await call_next(request)
    if request.url.path.startswith("/demo/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(demo_router)
app.include_router(alerts_router)
app.include_router(auth_router)
app.include_router(businesses_router)
app.include_router(employees_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(checkout_router)
app.include_router(mercado_pago_router)
app.include_router(conversations_router)
app.include_router(whatsapp_router)
app.include_router(whatsapp_settings_router)

panel_directory = Path(__file__).resolve().parents[2] / "frontend" / "public"
if (panel_directory / "index.html").is_file():
    app.mount("/panel", StaticFiles(directory=panel_directory, html=True), name="panel")

@app.get("/")
def root():
    return {
        "message": "AI Customer Assistant API funcionando"
    }