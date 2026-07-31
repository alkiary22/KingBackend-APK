import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from bson import json_util
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

async def backup():
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path.home() / "KingBackups" / ts
    out.mkdir(parents=True, exist_ok=True)

    collections = await db.list_collection_names()

    print(f"📦 سيتم نسخ {len(collections)} Collections")

    for name in collections:
        docs = await db[name].find({}, {"_id": False}).to_list(None)

        with open(out / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2, default=json_util.default)

        print(f"✅ {name}: {len(docs)} سجل")

    print()
    print("===================================")
    print("✅ Backup completed")
    print(out)
    print("===================================")

asyncio.run(backup())
