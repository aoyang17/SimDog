from __future__ import annotations

import json
import sys

request = json.load(sys.stdin)
json.dump(
    {
        "protocol_version": "simdog.agent.v1",
        "request_id": request["request_id"],
        "status": "completed",
        "provider": {"id": "fixture", "version": "1", "model": "none"},
        "artifacts": [
            {
                "name": "answer.json",
                "media_type": "application/json",
                "content": {"role": request["role"], "objective": request["objective"]},
            }
        ],
        "events": [],
        "usage": {},
        "error": None
    },
    sys.stdout,
)
