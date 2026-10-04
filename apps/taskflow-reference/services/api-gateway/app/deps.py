import os

import httpx
from fastapi import Header, HTTPException

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:8001")


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Extracts the bearer token from the Authorization header and verifies
    it against the Auth/User Service over the network on every protected
    request. This is a real runtime call, not local JWT decoding, so the
    API <-> Auth/User Service edge is exercised on every authenticated
    request, not just at login."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(f"{AUTH_SERVICE_URL}/verify", json={"token": token})
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"auth-service unreachable: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="auth-service returned an unexpected error")

    data = resp.json()
    if not data.get("valid"):
        raise HTTPException(status_code=401, detail="invalid or expired token")

    return {"user_id": data["user_id"], "username": data["username"]}
