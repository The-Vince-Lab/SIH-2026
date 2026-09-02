"""QA cleanup: remove trainees/enrollments/employment created during UI testing."""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or env["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME") or env["DB_NAME"]


async def main():
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    qa = await db.trainees.find({"full_name": {"$regex": "^QA_"}}, {"_id": 1, "full_name": 1}).to_list(500)
    ids = [t["_id"] for t in qa]
    print("QA trainees:", [t["full_name"] for t in qa])
    if ids:
        print("enrollments deleted:", (await db.enrollments.delete_many({"trainee_id": {"$in": ids}})).deleted_count)
        print("followups deleted:", (await db.followups.delete_many({"trainee_id": {"$in": ids}})).deleted_count)
        print("employment deleted:", (await db.employment_records.delete_many({"trainee_id": {"$in": ids}})).deleted_count)
        print("consent deleted:", (await db.consent_logs.delete_many({"trainee_id": {"$in": ids}})).deleted_count)
        print("trainees deleted:", (await db.trainees.delete_many({"_id": {"$in": ids}})).deleted_count)
    print("QA employer records deleted:",
          (await db.employment_records.delete_many({"employer_name": "QA_Test Employer Pvt Ltd"})).deleted_count)
    print("remaining trainees:", await db.trainees.count_documents({}))
    print("remaining QA:", await db.trainees.count_documents({"full_name": {"$regex": "QA_"}}))
    print("employment records:", await db.employment_records.count_documents({}))
    print("collections:", await db.list_collection_names())

asyncio.run(main())
