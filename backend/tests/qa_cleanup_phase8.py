"""QA cleanup (phase 8): removes QA_ trainees AND anonymized QA trainees.

Anonymized trainees lose their QA_ name, so we match them via the consent_logs
audit rows that reference them (or the 'Anonymized Trainee #' name pattern).
Seed trainees are never anonymized by design, so the name pattern is safe.
"""
import asyncio
import os

from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or env["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME") or env["DB_NAME"]


async def main():
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    q = {"$or": [{"full_name": {"$regex": "^QA_"}},
                 {"full_name": {"$regex": "^Anonymized Trainee #"}}]}
    qa = await db.trainees.find(q, {"_id": 1, "full_name": 1}).to_list(500)
    ids = [t["_id"] for t in qa]
    print("matched:", [t["full_name"] for t in qa])
    if ids:
        enr = [e["_id"] for e in await db.enrollments.find({"trainee_id": {"$in": ids}}, {"_id": 1}).to_list(2000)]
        print("followups:", (await db.followups.delete_many(
            {"$or": [{"trainee_id": {"$in": ids}}, {"enrollment_id": {"$in": enr}}]})).deleted_count)
        print("enrollments:", (await db.enrollments.delete_many({"trainee_id": {"$in": ids}})).deleted_count)
        print("employment:", (await db.employment_records.delete_many({"trainee_id": {"$in": ids}})).deleted_count)
        print("non_placement:", (await db.non_placement_reasons.delete_many({"trainee_id": {"$in": ids}})).deleted_count)
        print("consent_logs:", (await db.consent_logs.delete_many({"trainee_id": {"$in": ids}})).deleted_count)
        print("trainees:", (await db.trainees.delete_many({"_id": {"$in": ids}})).deleted_count)
    print("remaining trainees:", await db.trainees.count_documents({}))
    print("remaining QA/anon:", await db.trainees.count_documents(q))
    print("anonymized flag rows:", await db.trainees.count_documents({"anonymized": True}))
    print("login_attempts:", (await db.login_attempts.delete_many({})).deleted_count)


asyncio.run(main())
