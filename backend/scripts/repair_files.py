"""Check every db.files record against object storage. Dry run by default; never deletes or overwrites objects.

Usage:  python3 scripts/repair_files.py            # report only
        python3 scripts/repair_files.py --apply    # fix content types / paths in DB only
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import storage  # noqa: E402

APPLY = "--apply" in sys.argv


def _exists(path):
    try:
        data, ctype = storage.get_object(path)
        return data, ctype
    except Exception:
        return None, None


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    storage.init_storage()
    ok = fixed = 0
    missing = []
    async for f in db.files.find({"is_deleted": {"$ne": True}}, {"_id": 0}):
        path = f.get("storage_path") or ""
        data, _ = await asyncio.to_thread(_exists, path)
        upd = {}
        if data is None:
            ext = path.rsplit(".", 1)[-1] if "." in path else ""
            candidates = [f"{storage.APP_NAME}/uploads/{f.get('uploaded_by')}/{f['id']}.{e}" for e in {ext, "jpg", "jpeg", "png", "pdf", "webp"} if e]
            for c in candidates:
                if c != path:
                    data, _ = await asyncio.to_thread(_exists, c)
                    if data is not None:
                        upd["storage_path"] = c
                        break
        if data is None:
            missing.append((f["id"], path, f.get("project_id"), f.get("original_filename")))
            continue
        ext = (upd.get("storage_path") or path).rsplit(".", 1)[-1].lower()
        want = storage.MIME_TYPES.get(ext)
        if want and f.get("content_type") != want:
            upd["content_type"] = want
        if upd:
            print(("FIX " if APPLY else "WOULD FIX ") + f"{f['id']}: {upd}")
            if APPLY:
                await db.files.update_one({"id": f["id"]}, {"$set": upd})
            fixed += 1
        else:
            ok += 1
    print(f"\nOK: {ok}  {'fixed' if APPLY else 'fixable'}: {fixed}  missing in storage: {len(missing)}")
    for m in missing:
        print("MISSING", *m)
    if not APPLY:
        print("\nDry run only. Re-run with --apply to update database records (storage objects are never touched).")


asyncio.run(main())
