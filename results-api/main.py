import os

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from psycopg import Error as PsycopgError

CHOICES = ("Dune 3", "Doomsday")

app = FastAPI(title="Movie Voting Results")


class VoteCount(BaseModel):
    choice: str
    votes: int


class ResultsResponse(BaseModel):
    question: str
    total_votes: int
    results: list[VoteCount]


def postgres_connection():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "votes"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    try:
        with postgres_connection() as connection:
            connection.execute("SELECT 1")
    except PsycopgError as exc:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable") from exc
    return {"status": "ok"}


@app.get("/results", response_model=ResultsResponse)
def get_results() -> ResultsResponse:
    try:
        with postgres_connection() as connection:
            rows = connection.execute(
                "SELECT choice, COUNT(*) FROM votes GROUP BY choice"
            ).fetchall()
    except PsycopgError as exc:
        raise HTTPException(
            status_code=503,
            detail="Results are not available; check PostgreSQL and the worker",
        ) from exc

    counts = {choice: 0 for choice in CHOICES}
    for choice, count in rows:
        if choice in counts:
            counts[choice] = count

    results = [VoteCount(choice=choice, votes=counts[choice]) for choice in CHOICES]
    return ResultsResponse(
        question="Which movie will gross the most in December 2026?",
        total_votes=sum(counts.values()),
        results=results,
    )
