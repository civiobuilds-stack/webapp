"""Re-apply SUPERADMIN_INITIAL_PASSWORD to the Super Admin and require a change on next login."""
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent.parent / ".env")
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from auth import hash_password  # noqa: E402


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    r = await db.users.update_one({"email": os.environ["ADMIN_EMAIL"].lower()}, {"$set": {
        "password_hash": hash_password(os.environ["SUPERADMIN_INITIAL_PASSWORD"]), "must_change_password": True}})
    print("updated" if r.modified_count else "no change")

asyncio.run(main())
