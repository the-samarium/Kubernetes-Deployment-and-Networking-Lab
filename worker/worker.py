import logging
import os
import socket
import time
from datetime import datetime

import psycopg
from psycopg import Error as PsycopgError
from redis import Redis
from redis.exceptions import RedisError, ResponseError

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
VOTE_STREAM = os.getenv("VOTE_STREAM", "votes")
CONSUMER_GROUP = os.getenv("VOTE_CONSUMER_GROUP", "vote-workers")
CONSUMER_NAME = os.getenv("VOTE_CONSUMER_NAME", f"{socket.gethostname()}-{os.getpid()}")
CLAIM_IDLE_MS = 60_000

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

redis_client = Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_timeout=15,
    socket_connect_timeout=5,
)


def postgres_connection():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "votes"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


def initialize_database() -> None:
    with postgres_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS votes (
                vote_id UUID PRIMARY KEY,
                choice TEXT NOT NULL CHECK (choice IN ('Dune 3', 'Doomsday')),
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )


def save_vote(message_id: str, fields: dict[str, str]) -> None:
    try:
        vote_id = fields["vote_id"]
        choice = fields["choice"]
        created_at = datetime.fromisoformat(fields["created_at"])
        if choice not in ("Dune 3", "Doomsday"):
            raise ValueError(f"Unexpected vote choice: {choice!r}")
    except (KeyError, ValueError) as exc:
        logger.error("Discarding invalid vote message %s: %s", message_id, exc)
        redis_client.xack(VOTE_STREAM, CONSUMER_GROUP, message_id)
        return

    with postgres_connection() as connection:
        connection.execute(
            """
            INSERT INTO votes (vote_id, choice, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (vote_id) DO NOTHING
            """,
            (vote_id, choice, created_at),
        )
    redis_client.xack(VOTE_STREAM, CONSUMER_GROUP, message_id)
    logger.info("Processed vote %s", vote_id)


def process_messages(messages: list[tuple[str, dict[str, str]]]) -> None:
    for message_id, fields in messages:
        try:
            save_vote(message_id, fields)
        except (PsycopgError, RedisError):
            logger.exception("Could not process vote stream message %s", message_id)


def reclaim_pending_messages() -> None:
    cursor = "0-0"
    while True:
        cursor, messages, _ = redis_client.xautoclaim(
            VOTE_STREAM,
            CONSUMER_GROUP,
            CONSUMER_NAME,
            min_idle_time=CLAIM_IDLE_MS,
            start_id=cursor,
            count=10,
        )
        process_messages(messages)
        if cursor == "0-0":
            return


def main() -> None:
    while True:
        try:
            initialize_database()
            try:
                redis_client.xgroup_create(
                    VOTE_STREAM, CONSUMER_GROUP, id="0-0", mkstream=True
                )
            except ResponseError as exc:
                if not str(exc).startswith("BUSYGROUP"):
                    raise
            break
        except (PsycopgError, RedisError):
            logger.exception("Dependencies not ready; retrying initialization in 5s")
            time.sleep(5)

    logger.info("Worker %s is consuming votes", CONSUMER_NAME)
    while True:
        try:
            reclaim_pending_messages()
            messages = redis_client.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {VOTE_STREAM: ">"},
                count=10,
                block=5_000,
            )
            for _, stream_messages in messages:
                process_messages(stream_messages)
        except (PsycopgError, RedisError):
            logger.exception("Worker loop failed; retrying in 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
