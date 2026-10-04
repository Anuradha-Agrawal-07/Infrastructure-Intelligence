from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def build_realtime_router(
    realtime_service,
    connection_manager,
):
    router = APIRouter()

    @router.websocket("/ws/incidents/{incident_id}")
    async def incident_websocket(
        websocket: WebSocket,
        incident_id: UUID,
    ):
        await connection_manager.connect(
            incident_id,
            websocket,
        )

        try:
            last_sequence = 0

            # Optional client subscription message.
            try:
                raw = await websocket.receive_text()

                message = json.loads(raw)

                if message.get("type") == "SUBSCRIBE":
                    requested_incident = message.get(
                        "incident_id",
                    )

                    if requested_incident:
                        if str(incident_id) != str(
                            requested_incident
                        ):
                            await websocket.close(
                                code=1008,
                                reason="incident_id mismatch",
                            )
                            return

                    last_sequence = int(
                        message.get(
                            "last_sequence",
                            0,
                        )
                    )
            except Exception:
                # A client may connect without sending a
                # subscription payload immediately.
                last_sequence = 0

            # Catch up from PostgreSQL durable state.
            missed = realtime_service.catch_up(
                incident_id,
                after_sequence=last_sequence,
            )

            from_sequence = (
                missed[0].sequence
                if missed
                else last_sequence
            )

            to_sequence = (
                missed[-1].sequence
                if missed
                else last_sequence
            )

            for event in missed:
                await websocket.send_json(
                    event.to_ws_message()
                )

            await websocket.send_json(
                {
                    "type": "CATCH_UP_COMPLETE",
                    "incident_id": str(incident_id),
                    "from_sequence": from_sequence,
                    "to_sequence": to_sequence,
                }
            )

            # Keep connection alive and accept future
            # client subscription/control messages.
            while True:
                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    break

                if not raw:
                    continue

                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if message.get("type") == "SUBSCRIBE":
                    resume_sequence = int(
                        message.get(
                            "last_sequence",
                            0,
                        )
                    )

                    missed = realtime_service.catch_up(
                        incident_id,
                        after_sequence=resume_sequence,
                    )

                    for event in missed:
                        await websocket.send_json(
                            event.to_ws_message()
                        )

                    await websocket.send_json(
                        {
                            "type": "CATCH_UP_COMPLETE",
                            "incident_id": str(
                                incident_id
                            ),
                            "from_sequence": (
                                missed[0].sequence
                                if missed
                                else resume_sequence
                            ),
                            "to_sequence": (
                                missed[-1].sequence
                                if missed
                                else resume_sequence
                            ),
                        }
                    )

        except WebSocketDisconnect:
            pass
        finally:
            connection_manager.disconnect(
                incident_id,
                websocket,
            )

    return router
