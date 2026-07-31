import asyncio
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import os

load_dotenv()

client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
db = client[os.getenv("DB_NAME")]

async def main():
    total = await db.matches.count_documents({})
    missing = await db.matches.count_documents({
        "competition": {"$exists": False}
    })

    print(f"إجمالي المباريات : {total}")
    print(f"بدون competition : {missing}")

    if missing == 0:
        print("✅ لا يوجد شيء للتحديث")
        return

    result = await db.matches.update_many(
        {"competition": {"$exists": False}},
        {"$set": {"competition": "worldcup"}}
    )

    print(f"✅ تم تحديث {result.modified_count} مباراة")

    remaining = await db.matches.count_documents({
        "competition": {"$exists": False}
    })

    print(f"المتبقي بدون competition : {remaining}")

asyncio.run(main())
