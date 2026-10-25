import os
from datetime import datetime, timezone
from uuid import uuid4
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from redis import Redis
from redis.exceptions import RedisError

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
VOTE_STREAM = os.getenv("VOTE_STREAM", "votes")

redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
app = FastAPI(title="Movie Voting API")


class VoteRequest(BaseModel):
    choice: Literal["Dune 3", "Doomsday"]


class VoteAccepted(BaseModel):
    vote_id: str
    status: str


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    try:
        redis_client.ping()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Redis is unavailable") from exc
    return {"status": "ok"}


@app.post("/votes", response_model=VoteAccepted, status_code=status.HTTP_202_ACCEPTED)
def submit_vote(vote: VoteRequest) -> VoteAccepted:
    vote_id = str(uuid4())
    try:
        redis_client.xadd(
            VOTE_STREAM,
            {
                "vote_id": vote_id,
                "choice": vote.choice,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Could not queue the vote") from exc
    return VoteAccepted(vote_id=vote_id, status="queued")
