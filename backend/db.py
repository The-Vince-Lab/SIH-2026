"""MongoDB connection helpers and index creation for SkillTrace AI."""
import os

from motor.motor_asyncio import AsyncIOMotorClient


def get_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(os.environ["MONGO_URL"])


def get_db(client: AsyncIOMotorClient):
    return client[os.environ["DB_NAME"]]


async def ensure_indexes(db) -> None:
    """Create indexes for frequent lookups. Idempotent."""
    await db.users.create_index("email", unique=True)
    await db.trainees.create_index("phone_number")
    await db.trainees.create_index("district")
    await db.enrollments.create_index("trainee_id")
    await db.enrollments.create_index("program_id")
    await db.followups.create_index("trainee_id")
    await db.followups.create_index("enrollment_id")
    await db.employment_records.create_index("trainee_id")
    await db.non_placement_reasons.create_index("trainee_id")
    await db.training_programs.create_index("provider_id")
    await db.consent_logs.create_index("trainee_id")
    await db.login_attempts.create_index("identifier")
    await db.login_attempts.create_index("expires_at", expireAfterSeconds=0)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
