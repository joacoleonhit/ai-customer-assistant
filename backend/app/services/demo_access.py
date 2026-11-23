"""Explicit demo permissions: simulated workspaces cannot connect external services."""
import re
from fastapi import HTTPException


def check_demo_route(method, path):
    rules = {
        "GET": [r"/auth/me", r"/demo/state", r"/businesses/me", r"/products/", r"/orders/(?:[0-9]+)?", r"/alerts/", r"/conversations/(?:[^/]+)?"],
        "POST": [r"/demo/(?:messages|process)", r"/demo/orders/[0-9]+/payment", r"/products/"],
        "PATCH": [r"/products/[0-9]+/status", r"/orders/[0-9]+/status", r"/alerts/[0-9]+/resolve", r"/conversations/demo:[^/]+/attention"],
    }
    if not any(re.fullmatch(rule, path) for rule in rules.get(method, [])):
        raise HTTPException(403, "La demo usa datos ficticios y no permite conexiones ni pagos reales")
