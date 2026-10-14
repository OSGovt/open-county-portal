"""Staff console. Every page requires sign-in with a password and a
six-digit code; each section also checks the user's role."""
from fastapi import APIRouter

from . import account, content, counter, dashboard, finance, queues, records_admin, settings_pages, system

router = APIRouter(prefix="/staff", include_in_schema=False)
for module in (account, dashboard, counter, finance, content, queues, records_admin, settings_pages, system):
    router.include_router(module.router)
