from pathlib import Path

f = Path("server.py")

if not f.exists():
    print("❌ server.py غير موجود")
    raise SystemExit(1)

txt = f.read_text(encoding="utf-8")

checks = [
    "@api_router.post(\"/admin/import-new-fixtures\")",
    "async def import_new_fixtures",
    "@api_router.get(\"/external/live-matches\")",
    "API_FOOTBALL_KEY",
]

ok = True
for c in checks:
    if c in txt:
        print("✅", c)
    else:
        print("❌", c)
        ok = False

print("\nالحجم:", len(txt), "حرف")

if ok:
    print("\n✅ الملف مطابق ويمكن متابعة التعديل")
else:
    print("\n⛔ لا نعدل الملف قبل معرفة سبب الاختلاف")
