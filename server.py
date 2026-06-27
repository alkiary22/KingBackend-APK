from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict

from teams_data import WORLD_CUP_TEAMS
from fixtures_data import GROUP_FIXTURES, GROUP_LABEL
from sportsdb import fetch_world_cup_events, normalize_team_code, parse_score, FINISHED_STATUSES
from content_defaults import DEFAULT_CONTENT
import asyncio
import httpx

# Firebase Cloud Messaging
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:
    firebase_admin = None
    credentials = None
    messaging = None



TEAM_AR_NAMES = {
    "Arsenal": "أرسنال",
    "Paris Saint Germain": "باريس سان جيرمان",
    "Paris Saint-Germain": "باريس سان جيرمان",
    "PSG": "باريس سان جيرمان",
    "Real Madrid": "ريال مدريد",
    "Barcelona": "برشلونة",
    "Atletico Madrid": "أتلتيكو مدريد",
    "Sevilla": "إشبيلية",
    "Villarreal": "فياريال",
    "Valencia": "فالنسيا",
    "Manchester City": "مانشستر سيتي",
    "Manchester United": "مانشستر يونايتد",
    "Liverpool": "ليفربول",
    "Chelsea": "تشيلسي",
    "Tottenham": "توتنهام",
    "Tottenham Hotspur": "توتنهام",
    "Newcastle": "نيوكاسل",
    "Newcastle United": "نيوكاسل",
    "Aston Villa": "أستون فيلا",
    "West Ham": "وست هام",
    "Leicester": "ليستر سيتي",
    "Everton": "إيفرتون",
    "Bayern Munich": "بايرن ميونخ",
    "Borussia Dortmund": "بوروسيا دورتموند",
    "Bayer Leverkusen": "باير ليفركوزن",
    "RB Leipzig": "لايبزيغ",
    "Juventus": "يوفنتوس",
    "Inter": "إنتر ميلان",
    "Inter Milan": "إنتر ميلان",
    "AC Milan": "ميلان",
    "Napoli": "نابولي",
    "AS Roma": "روما",
    "Lazio": "لاتسيو",
    "Atalanta": "أتالانتا",
    "Ajax": "أياكس",
    "PSV Eindhoven": "آيندهوفن",
    "Feyenoord": "فينورد",
    "Benfica": "بنفيكا",
    "FC Porto": "بورتو",
    "Sporting CP": "سبورتينغ لشبونة",
    "Celtic": "سيلتيك",
    "Rangers": "رينجرز",
    "Galatasaray": "غلطة سراي",
    "Fenerbahce": "فنربخشة",
    "Besiktas": "بشكتاش",
    "Al-Hilal Saudi FC": "الهلال",
    "Al-Hilal": "الهلال",
    "Al-Nassr": "النصر",
    "Al-Ittihad": "الاتحاد",
    "Al-Ahli Jeddah": "الأهلي",
    "Al Ahli": "الأهلي",
    "Argentina": "الأرجنتين",
    "Brazil": "البرازيل",
    "France": "فرنسا",
    "Germany": "ألمانيا",
    "Spain": "إسبانيا",
    "Portugal": "البرتغال",
    "England": "إنجلترا",
    "Italy": "إيطاليا",
    "Netherlands": "هولندا",
    "Morocco": "المغرب",
    "Egypt": "مصر",
    "Saudi Arabia": "السعودية",
    "Japan": "اليابان",
    "South Korea": "كوريا الجنوبية",
    "USA": "الولايات المتحدة",
    "United States": "الولايات المتحدة",
}

def team_ar_name(name):
    if not name:
        return name
    return TEAM_AR_NAMES.get(name, name)


# ---------- DB ----------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ.get('JWT_SECRET', 'change-me')
JWT_ALG = "HS256"
JWT_EXPIRE_DAYS = 30

# ---------- App ----------
app = FastAPI(title="ملك التوقعات API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)


# ---------- Models ----------
class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: Literal["user", "supervisor", "admin"] = "user"
    total_points: int = 0
    avatar: Optional[str] = None
    created_at: str


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AuthOut(BaseModel):
    user: UserPublic
    token: str

class PushTokenIn(BaseModel):
    token: str


class TeamModel(BaseModel):
    code: str
    name_ar: str
    name_en: str
    confederation: str


class MatchCreate(BaseModel):
    home_team: str  # team code
    away_team: str
    match_date: str  # ISO date string YYYY-MM-DD
    kickoff: str  # ISO datetime UTC
    stage: str = "مرحلة المجموعات"
    group_name: Optional[str] = None


class MatchUpdate(BaseModel):
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    match_date: Optional[str] = None
    kickoff: Optional[str] = None
    stage: Optional[str] = None
    group_name: Optional[str] = None


class MatchResultIn(BaseModel):
    home_score: int = Field(ge=0, le=30)
    away_score: int = Field(ge=0, le=30)


class MatchModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    home_team: str
    away_team: str
    match_date: str
    kickoff: str
    stage: str
    group_name: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: Literal["scheduled", "finished"] = "scheduled"
    result_updated_at: Optional[str] = None
    result_source: Optional[str] = None


class PredictionIn(BaseModel):
    match_id: str
    home_score: int = Field(ge=0, le=30)
    away_score: int = Field(ge=0, le=30)


class PredictionModel(BaseModel):
    id: str
    match_id: str
    user_id: str
    home_score: int
    away_score: int
    points: Optional[int] = None
    created_at: str


class LeaderboardEntry(BaseModel):
    user_id: str
    name: str
    total_points: int
    predictions_count: int
    exact_count: int = 0
    correct_outcome_count: int = 0
    rank: int
    avatar: Optional[str] = None


# ---------- Auth helpers ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="غير مصرّح")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALG])
        user_id = payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="انتهت صلاحية الجلسة")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="رمز غير صالح")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="المستخدم غير موجود")
    return user


async def require_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="صلاحيات المدير العامة مطلوبة")
    return user


async def require_staff(user=Depends(get_current_user)):
    """Admin OR supervisor can manage matches, results, view users."""
    if user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="صلاحيات الإشراف مطلوبة")
    return user


def user_to_public(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "email": doc["email"],
        "name": doc["name"],
        "role": doc.get("role", "user"),
        "total_points": doc.get("total_points", 0),
        "avatar": doc.get("avatar"),
        "created_at": doc["created_at"],
    }


# ---------- Scoring ----------
def calc_points(pred_h: int, pred_a: int, actual_h: int, actual_a: int) -> int:
    if pred_h == actual_h and pred_a == actual_a:
        return 3
    pred_diff = pred_h - pred_a
    actual_diff = actual_h - actual_a
    if (pred_diff > 0 and actual_diff > 0) or \
       (pred_diff < 0 and actual_diff < 0) or \
       (pred_diff == 0 and actual_diff == 0):
        return 1
    return 0


# ---------- Auth endpoints ----------
@api_router.post("/auth/register", response_model=AuthOut)
async def register(data: RegisterIn):
    email = data.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مسجّل مسبقاً")
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": user_id,
        "email": email,
        "name": data.name.strip(),
        "password_hash": hash_password(data.password),
        "role": "user",
        "total_points": 0,
        "created_at": now,
    }
    await db.users.insert_one(doc)
    token = create_token(user_id)
    return {"user": user_to_public(doc), "token": token}


@api_router.post("/auth/login", response_model=AuthOut)
async def login(data: LoginIn):
    email = data.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="البريد أو كلمة المرور غير صحيحة")
    token = create_token(user["id"])
    return {"user": user_to_public(user), "token": token}


@api_router.get("/auth/me", response_model=UserPublic)
async def me(user=Depends(get_current_user)):
    return user_to_public(user)


# ---------- Teams ----------
@api_router.get("/time")
async def get_server_time():
    """Returns authoritative server UTC time. Used by frontend to prevent device-clock tampering."""
    return {"now": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


@api_router.get("/teams", response_model=List[TeamModel])
async def get_teams():
    return WORLD_CUP_TEAMS


# ---------- Matches ----------
@api_router.get("/matches", response_model=List[MatchModel])
async def list_matches(date: Optional[str] = None):
    query = {}
    if date:
        query["match_date"] = date
    matches = await db.matches.find(query, {"_id": 0}).sort("kickoff", 1).to_list(1000)
    return matches


@api_router.post("/matches", response_model=MatchModel)
async def create_match(data: MatchCreate, _staff=Depends(require_staff)):
    if data.home_team == data.away_team:
        raise HTTPException(status_code=400, detail="لا يمكن أن يكون الفريقان متطابقين")
    codes = {t["code"] for t in WORLD_CUP_TEAMS}
    if data.home_team not in codes or data.away_team not in codes:
        raise HTTPException(status_code=400, detail="رمز فريق غير صالح")
    match = {
        "id": str(uuid.uuid4()),
        "home_team": data.home_team,
        "away_team": data.away_team,
        "match_date": data.match_date,
        "kickoff": data.kickoff,
        "stage": data.stage,
        "group_name": data.group_name,
        "home_score": None,
        "away_score": None,
        "status": "scheduled",
    }
    await db.matches.insert_one(match.copy())
    return match


@api_router.put("/matches/{match_id}", response_model=MatchModel)
async def update_match(match_id: str, data: MatchUpdate, _staff=Depends(require_staff)):
    match = await db.matches.find_one({"id": match_id}, {"_id": 0})
    if not match:
        raise HTTPException(status_code=404, detail="المباراة غير موجودة")
    updates = {k: v for k, v in data.model_dump(exclude_none=True).items()}
    if updates:
        await db.matches.update_one({"id": match_id}, {"$set": updates})
    updated = await db.matches.find_one({"id": match_id}, {"_id": 0})
    return updated


@api_router.delete("/matches/{match_id}")
async def delete_match(match_id: str, _staff=Depends(require_staff)):
    match = await db.matches.find_one({"id": match_id}, {"_id": 0})
    if not match:
        raise HTTPException(status_code=404, detail="المباراة غير موجودة")

    # خصم نقاط هذه المباراة من المستخدمين قبل حذف توقعاتها
    predictions = await db.predictions.find({"match_id": match_id}, {"_id": 0}).to_list(10000)
    for p in predictions:
        pts = p.get("points")
        if isinstance(pts, int) and pts != 0:
            await db.users.update_one(
                {"id": p["user_id"]},
                {"$inc": {"total_points": -pts}}
            )

    await db.matches.delete_one({"id": match_id})
    await db.predictions.delete_many({"match_id": match_id})

    return {"ok": True, "removed_predictions": len(predictions)}


@api_router.post("/matches/{match_id}/result", response_model=MatchModel)
async def set_match_result(match_id: str, data: MatchResultIn, _staff=Depends(require_staff)):
    match = await db.matches.find_one({"id": match_id}, {"_id": 0})
    if not match:
        raise HTTPException(status_code=404, detail="المباراة غير موجودة")
    await apply_match_result(match_id, data.home_score, data.away_score, source="manual")
    updated = await db.matches.find_one({"id": match_id}, {"_id": 0})
    return updated


# ---------- Predictions ----------
@api_router.post("/predictions", response_model=PredictionModel)
async def submit_prediction(data: PredictionIn, user=Depends(get_current_user)):
    match = await db.matches.find_one({"id": data.match_id}, {"_id": 0})
    if not match:
        raise HTTPException(status_code=404, detail="المباراة غير موجودة")
    if match.get("status") == "finished":
        raise HTTPException(status_code=400, detail="انتهت المباراة، التوقعات مغلقة")
    # Lock predictions after kickoff
    try:
        kickoff_dt = datetime.fromisoformat(match["kickoff"].replace("Z", "+00:00"))
        if kickoff_dt <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="بدأت المباراة، التوقعات مغلقة")
    except ValueError:
        pass

    existing = await db.predictions.find_one(
        {"match_id": data.match_id, "user_id": user["id"]}, {"_id": 0}
    )
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        await db.predictions.update_one(
            {"id": existing["id"]},
            {"$set": {"home_score": data.home_score, "away_score": data.away_score, "created_at": now}},
        )
        out = await db.predictions.find_one({"id": existing["id"]}, {"_id": 0})
        return out
    pred = {
        "id": str(uuid.uuid4()),
        "match_id": data.match_id,
        "user_id": user["id"],
        "home_score": data.home_score,
        "away_score": data.away_score,
        "points": None,
        "created_at": now,
    }
    await db.predictions.insert_one(pred.copy())
    return pred


@api_router.get("/predictions/me", response_model=List[PredictionModel])
async def my_predictions(user=Depends(get_current_user)):
    preds = await db.predictions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(10000)
    return preds


# ---------- Leaderboard ----------
@api_router.get("/leaderboard", response_model=List[LeaderboardEntry])
async def leaderboard():
    pipeline = [
        {"$match": {"role": {"$ne": "admin"}}},
        {"$project": {
            "_id": 0,
            "user_id": "$id",
            "name": 1,
            "avatar": 1,
            "total_points": {"$ifNull": ["$total_points", 0]},
        }},
        {"$lookup": {
            "from": "predictions",
            "let": {"uid": "$user_id"},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$user_id", "$$uid"]}}},
                {"$group": {
                    "_id": None,
                    "predictions_count": {"$sum": 1},
                    "exact_count": {
                        "$sum": {"$cond": [{"$eq": ["$points", 3]}, 1, 0]}
                    },
                    "correct_outcome_count": {
                        "$sum": {"$cond": [{"$eq": ["$points", 1]}, 1, 0]}
                    },
                    "tiebreak": {
                        "$sum": {
                            "$cond": [
                                {"$gt": ["$points", 0]},
                                {"$toLong": {"$ifNull": [{"$toDate": "$created_at"}, "1970-01-01T00:00:00Z"]}},
                                0
                            ]
                        }
                    }
                }}
            ],
            "as": "stats"
        }},
        {"$addFields": {
            "stats": {"$arrayElemAt": ["$stats", 0]}
        }},
        {"$addFields": {
            "predictions_count": {"$ifNull": ["$stats.predictions_count", 0]},
            "exact_count": {"$ifNull": ["$stats.exact_count", 0]},
            "correct_outcome_count": {"$ifNull": ["$stats.correct_outcome_count", 0]},
            "_tiebreak": {
                "$cond": [
                    {"$gt": [{"$ifNull": ["$stats.tiebreak", 0]}, 0]},
                    {"$ifNull": ["$stats.tiebreak", 0]},
                    999999999999999999
                ]
            }
        }},
        {"$sort": {
            "total_points": -1,
            "exact_count": -1,
            "correct_outcome_count": -1,
            "_tiebreak": 1
        }},
        {"$limit": 100},
        {"$project": {
            "user_id": 1,
            "name": 1,
            "avatar": 1,
            "total_points": 1,
            "predictions_count": 1,
            "exact_count": 1,
            "correct_outcome_count": 1
        }}
    ]

    rows = await db.users.aggregate(pipeline).to_list(100)

    out = []
    for i, r in enumerate(rows, start=1):
        out.append({
            "user_id": r["user_id"],
            "name": r["name"],
            "avatar": r.get("avatar"),
            "total_points": int(r.get("total_points", 0)),
            "predictions_count": int(r.get("predictions_count", 0)),
            "exact_count": int(r.get("exact_count", 0)),
            "correct_outcome_count": int(r.get("correct_outcome_count", 0)),
            "rank": i,
        })
    return out


# ---------- Stats ----------
@api_router.get("/stats/me")
async def my_stats(user=Depends(get_current_user)):
    preds = await db.predictions.find({"user_id": user["id"]}, {"_id": 0}).to_list(10000)
    total = len(preds)
    scored = [p for p in preds if isinstance(p.get("points"), int)]
    correct_exact = sum(1 for p in scored if p["points"] == 3)
    correct_outcome = sum(1 for p in scored if p["points"] == 1)
    accuracy = round(((correct_exact + correct_outcome) / len(scored)) * 100, 1) if scored else 0.0
    # rank
    rank_users = await db.users.find(
        {"role": {"$ne": "admin"}}, {"_id": 0, "id": 1, "total_points": 1}
    ).sort("total_points", -1).to_list(10000)
    rank = next((i + 1 for i, u in enumerate(rank_users) if u["id"] == user["id"]), None)
    return {
        "total_points": user.get("total_points", 0),
        "total_predictions": total,
        "correct_exact": correct_exact,
        "correct_outcome": correct_outcome,
        "accuracy": accuracy,
        "rank": rank,
    }


# ---------- Admin: list users ----------
@api_router.get("/admin/users")
async def list_users(_staff=Depends(require_staff)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(10000)
    # Add predictions count + ensure avatar key for legacy users
    out = []
    for u in users:
        count = await db.predictions.count_documents({"user_id": u["id"]})
        out.append({**u, "avatar": u.get("avatar"), "predictions_count": count})
    return out


class UserUpdateIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)



class AdminPasswordResetIn(BaseModel):
    new_password: str = Field(min_length=6, max_length=100)


class UserRoleIn(BaseModel):
    role: Literal["user", "supervisor", "admin"]


@api_router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, data: UserUpdateIn, admin=Depends(require_admin)):
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    await db.users.update_one({"id": user_id}, {"$set": {"name": data.name.strip()}})
    return {"ok": True}



@api_router.put("/admin/users/{user_id}/password")
async def admin_reset_user_password(user_id: str, data: AdminPasswordResetIn, admin=Depends(require_admin)):
    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    await db.users.update_one(
        {"id": user_id},
        {"$set": {"password_hash": hash_password(data.new_password)}}
    )
    return {"ok": True}


@api_router.put("/admin/users/{user_id}/role")
async def admin_set_role(user_id: str, data: UserRoleIn, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="لا يمكنك تغيير صلاحياتك الشخصية")
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    await db.users.update_one({"id": user_id}, {"$set": {"role": data.role}})
    return {"ok": True, "role": data.role}


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="لا يمكن حذف حسابك")
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    # Cascade delete (any user, including other admins)
    await db.predictions.delete_many({"user_id": user_id})
    await db.notifications.delete_many({"user_id": user_id})
    await db.users.delete_one({"id": user_id})
    return {"ok": True}


# ---------- Admin/Supervisor: view all predictions ----------
@api_router.get("/admin/predictions")
async def admin_list_predictions(
    match_id: Optional[str] = None,
    _staff=Depends(require_staff),
):
    """Admin & supervisor can view predictions made by all members.
    Optional filter by match_id. Returns enriched rows with user + match info.
    """
    query = {}
    if match_id:
        query["match_id"] = match_id

    preds = await db.predictions.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)

    # Build user + match lookup tables to enrich
    user_ids = list({p["user_id"] for p in preds})
    match_ids = list({p["match_id"] for p in preds})
    users = await db.users.find(
        {"id": {"$in": user_ids}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "avatar": 1, "role": 1},
    ).to_list(10000) if user_ids else []
    matches = await db.matches.find(
        {"id": {"$in": match_ids}},
        {"_id": 0, "id": 1, "home_team": 1, "away_team": 1, "kickoff_utc": 1,
         "status": 1, "home_score": 1, "away_score": 1, "group": 1},
    ).to_list(10000) if match_ids else []
    umap = {u["id"]: u for u in users}
    mmap = {m["id"]: m for m in matches}

    rows = []
    for p in preds:
        u = umap.get(p["user_id"], {})
        m = mmap.get(p["match_id"], {})
        rows.append({
            "id": p.get("id"),
            "match_id": p["match_id"],
            "user_id": p["user_id"],
            "user_name": u.get("name"),
            "user_email": u.get("email"),
            "user_avatar": u.get("avatar"),
            "user_role": u.get("role"),
            "pred_home": p["home_score"],
            "pred_away": p["away_score"],
            "points": p.get("points"),  # may be None when match not yet finished
            "created_at": p.get("created_at"),
            "match": {
                "home_team": m.get("home_team"),
                "away_team": m.get("away_team"),
                "kickoff_utc": m.get("kickoff_utc"),
                "status": m.get("status"),
                "home_score": m.get("home_score"),
                "away_score": m.get("away_score"),
                "group": m.get("group"),
            } if m else None,
        })
    return {"count": len(rows), "items": rows}




# ---------- Auto-sync results (TheSportsDB - free) ----------
async def create_notifications_for_match(match: dict, home_score: int, away_score: int, source: str):
    """Create per-user notifications for all users who predicted this match."""
    predictions = await db.predictions.find({"match_id": match["id"]}, {"_id": 0}).to_list(10000)
    now_iso = datetime.now(timezone.utc).isoformat()
    notifs = []
    for p in predictions:
        pts = calc_points(p["home_score"], p["away_score"], home_score, away_score)
        notifs.append({
            "id": str(uuid.uuid4()),
            "user_id": p["user_id"],
            "type": "match_result",
            "match_id": match["id"],
            "payload": {
                "home_team": match["home_team"],
                "away_team": match["away_team"],
                "home_score": home_score,
                "away_score": away_score,
                "pred_home": p["home_score"],
                "pred_away": p["away_score"],
                "points": pts,
                "source": source,
            },
            "read": False,
            "created_at": now_iso,
        })
    if notifs:
        await db.notifications.insert_many(notifs)
        for n in notifs:
            pts = n.get("payload", {}).get("points", 0)
            await send_push_to_user(
                n["user_id"],
                "نتيجة المباراة 🏁",
                f"تم احتساب نتيجتك: {pts} نقطة",
                {"type": "match_result", "match_id": n["match_id"]}
            )


async def apply_match_result(match_id: str, home_score: int, away_score: int, source: str = "manual"):
    """Update match status + recompute prediction points + adjust user totals (delta-aware).
    Also creates user notifications and stamps update time."""
    match = await db.matches.find_one({"id": match_id}, {"_id": 0})
    if not match:
        return
    was_finished = match.get("status") == "finished"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.matches.update_one(
        {"id": match_id},
        {"$set": {
            "home_score": home_score,
            "away_score": away_score,
            "status": "finished",
            "result_updated_at": now_iso,
            "result_source": source,
        }},
    )
    predictions = await db.predictions.find({"match_id": match_id}, {"_id": 0}).to_list(10000)
    for p in predictions:
        pts = calc_points(p["home_score"], p["away_score"], home_score, away_score)
        old_pts = p.get("points")
        await db.predictions.update_one({"id": p["id"]}, {"$set": {"points": pts}})
        delta = pts - (old_pts if isinstance(old_pts, int) else 0)
        if delta:
            await db.users.update_one({"id": p["user_id"]}, {"$inc": {"total_points": delta}})
    # Create notifications only on first-time finalization (avoid spam on edits)
    if not was_finished:
        await create_notifications_for_match({**match, "id": match_id}, home_score, away_score, source)


async def sync_results_from_thesportsdb():
    """Pull finished events from TheSportsDB and apply results to matching matches."""
    sync_start = datetime.now(timezone.utc).isoformat()
    try:
        events = await fetch_world_cup_events()
    except Exception as e:
        logger.warning(f"TheSportsDB fetch failed: {e}")
        await db.app_state.update_one(
            {"key": "last_sync"},
            {"$set": {"key": "last_sync", "at": sync_start, "ok": False, "error": str(e), "updated": 0}},
            upsert=True,
        )
        return {"updated": 0, "checked": 0, "error": str(e), "synced_at": sync_start}

    updated = 0
    checked = 0
    for ev in events:
        status = (ev.get("strStatus") or "").strip().lower()
        if status not in FINISHED_STATUSES:
            continue
        checked += 1
        h_score = parse_score(ev.get("intHomeScore"))
        a_score = parse_score(ev.get("intAwayScore"))
        if h_score is None or a_score is None:
            continue
        h_code = normalize_team_code(ev.get("strHomeTeam"))
        a_code = normalize_team_code(ev.get("strAwayTeam"))
        if not h_code or not a_code:
            continue
        logger.info(f"SYNC TRY: {ev.get('strHomeTeam')}({h_code}) vs {ev.get('strAwayTeam')}({a_code}) score {h_score}-{a_score}")

        match = await db.matches.find_one(
            {"home_team": h_code, "away_team": a_code, "status": {"$ne": "finished"}},
            {"_id": 0},
        )
        if not match:
            match = await db.matches.find_one(
                {"home_team": a_code, "away_team": h_code, "status": {"$ne": "finished"}},
                {"_id": 0},
            )
            if match:
                h_score, a_score = a_score, h_score
        if not match:
            logger.info(f"SYNC NO MATCH: {h_code} vs {a_code}")
            continue
        await apply_match_result(match["id"], h_score, a_score, source="auto")
        updated += 1
    if updated:
        logger.info(f"Auto-sync: applied {updated} results (checked {checked} finished events)")
    await db.app_state.update_one(
        {"key": "last_sync"},
        {"$set": {"key": "last_sync", "at": sync_start, "ok": True, "updated": updated, "checked": checked}},
        upsert=True,
    )
    return {"updated": updated, "checked": checked, "synced_at": sync_start}


# AUTO_SYNC_RESULTS_TASK
async def auto_sync_results_loop():
    while True:
        try:
            await sync_results_from_thesportsdb()
        except Exception as e:
            logger.warning(f"Auto sync loop failed: {e}")
        await asyncio.sleep(300)


@api_router.post("/admin/sync-results")
async def manual_sync_results(_staff=Depends(require_staff)):
    """Trigger immediate sync of finished match results from TheSportsDB."""
    return await sync_results_from_thesportsdb()


@api_router.get("/admin/test-api-football")
async def test_api_football(_staff=Depends(require_staff)):
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        return {"ok": False, "error": "API_FOOTBALL_KEY غير موجود"}

    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": api_key}
    params = {"date": "2026-06-15", "league": 1, "season": 2026}

    async with httpx.AsyncClient(timeout=20) as client_http:
        r = await client_http.get(url, headers=headers, params=params)

    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "body": r.text[:500]}

    data = r.json()
    items = []

    for item in data.get("response", [])[:20]:
        fixture = item.get("fixture", {}) or {}
        status = fixture.get("status", {}) or {}
        teams = item.get("teams", {}) or {}
        goals = item.get("goals", {}) or {}
        league = item.get("league", {}) or {}

        items.append({
            "league": league.get("name"),
            "home": (teams.get("home") or {}).get("name"),
            "away": (teams.get("away") or {}).get("name"),
            "home_score": goals.get("home"),
            "away_score": goals.get("away"),
            "status": status.get("short"),
            "status_long": status.get("long"),
        })

    return {"ok": True, "count": len(data.get("response", [])), "items": items}


@api_router.get("/admin/last-sync")
async def get_last_sync(_staff=Depends(require_staff)):
    doc = await db.app_state.find_one({"key": "last_sync"}, {"_id": 0})
    return doc or {"at": None, "ok": None, "updated": 0, "checked": 0}


# ---------- Site Content (editable text) ----------
@api_router.get("/content")
async def get_content():
    """Public: returns merged content (defaults + overrides)."""
    overrides_doc = await db.app_state.find_one({"key": "site_content"}, {"_id": 0})
    overrides = (overrides_doc or {}).get("values", {})
    merged = {**DEFAULT_CONTENT, **overrides}
    return {"defaults": DEFAULT_CONTENT, "values": merged}


class ContentUpdateIn(BaseModel):
    values: dict


@api_router.put("/admin/content")
async def update_content(data: ContentUpdateIn, _admin=Depends(require_admin)):
    """Admin only: overwrites overrides map. Pass empty {} to reset to defaults."""
    # keep only keys that exist in DEFAULT_CONTENT to prevent garbage
    clean = {k: str(v) for k, v in data.values.items() if k in DEFAULT_CONTENT}
    await db.app_state.update_one(
        {"key": "site_content"},
        {"$set": {"key": "site_content", "values": clean}},
        upsert=True,
    )
    return {"ok": True, "count": len(clean)}


# ---------- Ads Slider ----------
class AdsSliderIn(BaseModel):
    images: list[str] = Field(default_factory=list, max_length=8)


@api_router.get("/ads-slider")
async def get_ads_slider():
    doc = await db.app_state.find_one({"key": "ads_slider"}, {"_id": 0})
    images = (doc or {}).get("images") or []
    return {"images": images}


@api_router.put("/admin/ads-slider")
async def update_ads_slider(data: AdsSliderIn, _admin=Depends(require_admin)):
    clean = []
    for img in data.images[:8]:
        if not isinstance(img, str):
            continue
        if not img.startswith("data:image/"):
            continue
        if len(img) > 700_000:
            raise HTTPException(status_code=400, detail="حجم الصورة كبير جدًا")
        clean.append(img)

    await db.app_state.update_one(
        {"key": "ads_slider"},
        {"$set": {"key": "ads_slider", "images": clean, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "count": len(clean)}


# ---------- Avatar (per-user) ----------
class AvatarIn(BaseModel):
    avatar: str = Field(min_length=20, max_length=350_000)  # base64 data URL


@api_router.post("/users/me/avatar")
async def upload_avatar(data: AvatarIn, user=Depends(get_current_user)):
    """Store base64 data-URL avatar (resized client-side). Max ~250KB raw."""
    if not data.avatar.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="صيغة الصورة غير صحيحة")
    await db.users.update_one({"id": user["id"]}, {"$set": {"avatar": data.avatar}})
    return {"ok": True}


@api_router.delete("/users/me/avatar")
async def remove_avatar(user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$set": {"avatar": None}})
    return {"ok": True}


# ---------- Push Notifications ----------
FCM_READY = False

def init_fcm():
    global FCM_READY
    if FCM_READY:
        return True
    if firebase_admin is None:
        logger.warning("firebase-admin not installed")
        return False
    key_path = ROOT_DIR / "serviceAccountKey.json"
    if not key_path.exists():
        logger.warning("serviceAccountKey.json not found")
        return False
    if not firebase_admin._apps:
        cred = credentials.Certificate(str(key_path))
        firebase_admin.initialize_app(cred)
    FCM_READY = True
    return True


def build_push_link(path: str | None = None):
    base = os.environ.get("FRONTEND_URL", "https://king-of-predictions-17019.web.app").rstrip("/")
    target = str(path or "/").strip()
    if not target:
        target = "/"
    if target.startswith("http://") or target.startswith("https://"):
        return target
    if not target.startswith("/"):
        target = "/" + target
    return base + target

async def send_push_to_user(user_id: str, title: str, body: str, data: dict | None = None):
    if not init_fcm():
        return {"sent": 0, "error": "FCM not ready"}

    tokens = await db.push_tokens.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    sent = 0

    for item in tokens:
        token = item.get("token")
        if not token:
            continue
        try:
            payload_data = {k: str(v) for k, v in (data or {}).items()}
            link = build_push_link(payload_data.get("url") or payload_data.get("link") or "/")
            msg = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
                webpush=messaging.WebpushConfig(
                    fcm_options=messaging.WebpushFCMOptions(link=link)
                ),
                token=token,
            )
            messaging.send(msg)
            sent += 1
        except Exception as e:
            logger.warning(f"FCM send failed: {e}")
            await db.push_tokens.delete_one({"token": token})

    return {"sent": sent}


class BroadcastPushIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=500)
    url: str | None = None


async def send_push_to_all_users(title: str, body: str, data: dict | None = None):
    if not init_fcm():
        return {"sent": 0, "failed": 0, "users": 0, "error": "FCM not ready"}

    tokens = await db.push_tokens.find({}, {"_id": 0, "token": 1, "user_id": 1}).to_list(50000)

    seen = set()
    unique_tokens = []
    user_ids = set()

    for item in tokens:
        token = item.get("token")
        uid = item.get("user_id")
        if uid:
            user_ids.add(uid)
        if not token or token in seen:
            continue
        seen.add(token)
        unique_tokens.append(token)

    sent = 0
    failed = 0

    for token in unique_tokens:
        try:
            payload_data = {k: str(v) for k, v in (data or {}).items()}
            link = build_push_link(payload_data.get("url") or payload_data.get("link") or "/")
            msg = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
                webpush=messaging.WebpushConfig(
                    fcm_options=messaging.WebpushFCMOptions(link=link)
                ),
                token=token,
            )
            messaging.send(msg)
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"FCM broadcast failed: {e}")
            await db.push_tokens.delete_one({"token": token})

    return {
        "sent": sent,
        "failed": failed,
        "tokens": len(unique_tokens),
        "users": len(user_ids),
    }


@api_router.post("/push/register-token")
async def register_push_token(data: PushTokenIn, user=Depends(get_current_user)):
    await db.push_tokens.update_one(
        {"token": data.token},
        {"$set": {
            "token": data.token,
            "user_id": user["id"],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    return {"ok": True}

@api_router.post("/push/test")
async def test_push(user=Depends(get_current_user)):
    return await send_push_to_user(
        user["id"],
        "ملك التوقعات",
        "تم تفعيل الإشعارات بنجاح ✅",
        {"type": "test"}
    )



@api_router.post("/admin/push/broadcast")
async def admin_broadcast_push(data: BroadcastPushIn, _staff=Depends(require_staff)):
    payload = {"type": "broadcast"}
    if data.url:
        payload["url"] = data.url

    result = await send_push_to_all_users(data.title, data.body, payload)
    return {"ok": True, **result}


@api_router.get("/push/me")
async def my_push_tokens(user=Depends(get_current_user)):
    tokens = await db.push_tokens.find(
        {"user_id": user["id"]},
        {"_id": 0, "token": 1, "updated_at": 1}
    ).to_list(100)
    return {
        "count": len(tokens),
        "items": tokens
    }


async def send_match_start_reminders(minutes_before: int = 15):
    """Send one reminder to all users for matches starting within the next minutes_before."""
    now = datetime.now(timezone.utc)
    target = now + timedelta(minutes=minutes_before)

    matches = await db.matches.find(
        {"status": {"$nin": ["live", "started", "finished", "ended"]}},
        {"_id": 0}
    ).to_list(10000)

    reminded = 0
    checked = 0

    users = await db.users.find({}, {"_id": 0, "id": 1}).to_list(10000)
    user_ids = [u.get("id") for u in users if u.get("id")]

    for match in matches:
        kickoff = match.get("kickoff_utc") or match.get("kickoff")
        if not kickoff:
            continue

        try:
            dt = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        # Match starts between now and 15 minutes from now
        if not (now <= dt <= target):
            continue

        checked += 1
        match_id = match.get("id")
        reminder_key = f"match_start_15_{match_id}"

        exists = await db.notifications.find_one(
            {"type": "match_start_reminder", "match_id": match_id, "payload.reminder_key": reminder_key},
            {"_id": 0, "id": 1}
        )
        if exists:
            continue

        home = match.get("home_team")
        away = match.get("away_team")
        now_iso = now.isoformat()

        notifs = []
        for uid in user_ids:
            notifs.append({
                "id": str(uuid.uuid4()),
                "user_id": uid,
                "type": "match_start_reminder",
                "match_id": match_id,
                "payload": {
                    "home_team": home,
                    "away_team": away,
                    "kickoff": kickoff,
                    "minutes_before": minutes_before,
                    "reminder_key": reminder_key,
                },
                "read": False,
                "created_at": now_iso,
            })

        if notifs:
            await db.notifications.insert_many(notifs)

        for uid in user_ids:
            await send_push_to_user(
                uid,
                "اقتربت المباراة ⏰",
                f"تبقّى {minutes_before} دقيقة على بداية المباراة. لا تنسَ توقعك!",
                {"type": "match_start_reminder", "match_id": match_id}
            )

        reminded += 1

    return {"ok": True, "checked_matches": checked, "reminded_matches": reminded, "users": len(user_ids)}


@api_router.post("/admin/send-match-reminders")
async def admin_send_match_reminders(_staff=Depends(require_staff)):
    """Admin/staff: send reminders for matches starting within 15 minutes."""
    return await send_match_start_reminders(15)


# AUTO_MATCH_REMINDERS_TASK
async def auto_match_reminders_loop():
    while True:
        try:
            await send_match_start_reminders(15)
        except Exception as e:
            logger.warning(f"Auto match reminders loop failed: {e}")
        await asyncio.sleep(60)

# ---------- Notifications ----------
@api_router.get("/notifications/me")
async def my_notifications(limit: int = 30, user=Depends(get_current_user)):
    notifs = await db.notifications.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    unread = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    return {"items": notifs, "unread": unread}


@api_router.post("/notifications/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    await db.notifications.update_many(
        {"user_id": user["id"], "read": False}, {"$set": {"read": True}}
    )
    return {"ok": True}


@api_router.post("/notifications/{notif_id}/read")
async def mark_one_read(notif_id: str, user=Depends(get_current_user)):
    await db.notifications.update_one(
        {"id": notif_id, "user_id": user["id"]}, {"$set": {"read": True}}
    )
    return {"ok": True}


async def auto_sync_loop():
    """Background task: sync every 15 minutes."""
    await asyncio.sleep(30)  # let app start first
    while True:
        try:
            await sync_results_from_thesportsdb()
        except Exception as e:
            logger.error(f"auto_sync_loop iteration error: {e}")
        await asyncio.sleep(900)  # 15 minutes


# ---------- Admin: seed official fixtures ----------
@api_router.post("/admin/seed-fixtures")
async def seed_fixtures(_admin=Depends(require_admin)):
    raise HTTPException(
        status_code=403,
        detail="تم تعطيل تحميل المباريات لحماية توقعات المستخدمين"
    )

    """Wipes existing matches + predictions and inserts the official
    72 group-stage fixtures of World Cup 2026."""
    await db.matches.delete_many({})
    await db.predictions.delete_many({})
    await db.notifications.delete_many({})
    # Reset user totals because predictions are wiped
    await db.users.update_many({"role": {"$ne": "admin"}}, {"$set": {"total_points": 0}})

    docs = []
    MECCA = timezone(timedelta(hours=3))
    for home, away, date_local, time_local, group in GROUP_FIXTURES:
        # Source times are treated as Mecca/Riyadh local time (UTC+3).
        # UTC = Mecca - 3h.
        h, mnt = map(int, time_local.split(":"))
        y, m, d = map(int, date_local.split("-"))
        mecca_dt = datetime(y, m, d, h, mnt, tzinfo=MECCA)
        kickoff_utc = mecca_dt.astimezone(timezone.utc)
        # match_date = Mecca-local date so users see it on the right day
        match_date_mecca = mecca_dt.strftime("%Y-%m-%d")
        docs.append({
            "id": str(uuid.uuid4()),
            "home_team": home,
            "away_team": away,
            "match_date": match_date_mecca,
            "kickoff": kickoff_utc.isoformat().replace("+00:00", "Z"),
            "stage": "مرحلة المجموعات",
            "group_name": GROUP_LABEL.get(group, group),
            "home_score": None,
            "away_score": None,
            "status": "scheduled",
        })
    if docs:
        await db.matches.insert_many([{**d} for d in docs])
    return {"inserted": len(docs)}


# ---------- Startup ----------

# ===== Challenge Bracket API =====

DEFAULT_CHALLENGE_ROUND32 = [
    {"id": "r32_1", "date": "الإثنين، 29 يونيو", "time": "23:30 مكة", "home": {"name": "كوت ديفوار", "flag": "🇨🇮"}, "away": {"name": "التشيك", "flag": "🇨🇿"}},
    {"id": "r32_2", "date": "الأربعاء، 1 يوليو", "time": "00:00 مكة", "home": {"name": "فرنسا", "flag": "🇫🇷"}, "away": {"name": "الرأس الأخضر", "flag": "🇨🇻"}},
    {"id": "r32_3", "date": "الأحد، 28 يونيو", "time": "22:00 مكة", "home": {"name": "كوريا الجنوبية", "flag": "🇰🇷"}, "away": {"name": "البوسنة", "flag": "🇧🇦"}},
    {"id": "r32_4", "date": "الثلاثاء، 30 يونيو", "time": "04:00 مكة", "home": {"name": "هولندا", "flag": "🇳🇱"}, "away": {"name": "البرازيل", "flag": "🇧🇷"}},
    {"id": "r32_5", "date": "الجمعة، 3 يوليو", "time": "02:00 مكة", "home": {"name": "أوزبكستان", "flag": "🇺🇿"}, "away": {"name": "كرواتيا", "flag": "🇭🇷"}},
    {"id": "r32_6", "date": "الخميس، 2 يوليو", "time": "22:00 مكة", "home": {"name": "إسبانيا", "flag": "🇪🇸"}, "away": {"name": "النمسا", "flag": "🇦🇹"}},
    {"id": "r32_7", "date": "الخميس، 2 يوليو", "time": "03:00 مكة", "home": {"name": "أستراليا", "flag": "🇦🇺"}, "away": {"name": "كندا", "flag": "🇨🇦"}},
    {"id": "r32_8", "date": "الأربعاء، 1 يوليو", "time": "23:00 مكة", "home": {"name": "المغرب", "flag": "🇲🇦"}, "away": {"name": "أمريكا", "flag": "🇺🇸"}},
    {"id": "r32_9", "date": "السبت، 4 يوليو", "time": "21:00 مكة", "home": {"name": "الأرجنتين", "flag": "🇦🇷"}, "away": {"name": "اليابان", "flag": "🇯🇵"}},
    {"id": "r32_10", "date": "الأحد، 5 يوليو", "time": "00:00 مكة", "home": {"name": "إنجلترا", "flag": "🏴"}, "away": {"name": "السنغال", "flag": "🇸🇳"}},
    {"id": "r32_11", "date": "الإثنين، 6 يوليو", "time": "22:00 مكة", "home": {"name": "ألمانيا", "flag": "🇩🇪"}, "away": {"name": "غانا", "flag": "🇬🇭"}},
    {"id": "r32_12", "date": "الثلاثاء، 7 يوليو", "time": "03:00 مكة", "home": {"name": "إيطاليا", "flag": "🇮🇹"}, "away": {"name": "مصر", "flag": "🇪🇬"}},
    {"id": "r32_13", "date": "الأربعاء، 8 يوليو", "time": "22:00 مكة", "home": {"name": "البرتغال", "flag": "🇵🇹"}, "away": {"name": "المكسيك", "flag": "🇲🇽"}},
    {"id": "r32_14", "date": "الخميس، 9 يوليو", "time": "23:00 مكة", "home": {"name": "أوروجواي", "flag": "🇺🇾"}, "away": {"name": "السعودية", "flag": "🇸🇦"}},
    {"id": "r32_15", "date": "الجمعة، 10 يوليو", "time": "22:00 مكة", "home": {"name": "بلجيكا", "flag": "🇧🇪"}, "away": {"name": "كولومبيا", "flag": "🇨🇴"}},
    {"id": "r32_16", "date": "السبت، 11 يوليو", "time": "00:00 مكة", "home": {"name": "سويسرا", "flag": "🇨🇭"}, "away": {"name": "الدنمارك", "flag": "🇩🇰"}},
]


class ChallengeTeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    flag: str = Field(min_length=1, max_length=12)


class ChallengeMatchIn(BaseModel):
    id: str
    date: str = Field(min_length=1, max_length=80)
    time: str = Field(min_length=1, max_length=80)
    home: ChallengeTeamIn
    away: ChallengeTeamIn


class ChallengeBracketIn(BaseModel):
    matches: List[ChallengeMatchIn]


@api_router.get("/challenge/bracket")
async def get_challenge_bracket():
    doc = await db.challenge_brackets.find_one(
        {"id": "worldcup2026_round32"},
        {"_id": 0}
    )

    if not doc:
        return {
            "id": "worldcup2026_round32",
            "matches": DEFAULT_CHALLENGE_ROUND32,
            "updated_at": None,
        }

    return doc


@api_router.put("/admin/challenge/bracket")
async def update_challenge_bracket(data: ChallengeBracketIn, _staff=Depends(require_staff)):
    if len(data.matches) != 16:
        raise HTTPException(status_code=400, detail="يجب أن يكون عدد مباريات دور الـ32 هو 16 مباراة")

    matches = []
    for m in data.matches:
        if hasattr(m, "model_dump"):
            matches.append(m.model_dump())
        else:
            matches.append(m.dict())

    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": "worldcup2026_round32",
        "matches": matches,
        "updated_at": now,
    }

    await db.challenge_brackets.update_one(
        {"id": "worldcup2026_round32"},
        {"$set": doc},
        upsert=True
    )

    return {"success": True, "updated_at": now, "matches": matches}

# ===== End Challenge Bracket API =====



# ===== Challenge Predictions, Results, Scores API =====

CHALLENGE_ID = "worldcup2026_round32"

CHALLENGE_POINTS = {
    "round32": 2,
    "round16": 4,
    "quarterFinals": 6,
    "semiFinals": 8,
    "champion": 15,
}


class ChallengePredictionIn(BaseModel):
    round32: dict = Field(default_factory=dict)
    round16: dict = Field(default_factory=dict)
    quarterFinals: dict = Field(default_factory=dict)
    semiFinals: dict = Field(default_factory=dict)
    final: dict = Field(default_factory=dict)
    champion: dict


class ChallengeResultsIn(BaseModel):
    round32: dict = Field(default_factory=dict)
    round16: dict = Field(default_factory=dict)
    quarterFinals: dict = Field(default_factory=dict)
    semiFinals: dict = Field(default_factory=dict)
    final: dict = Field(default_factory=dict)
    champion: dict


def _team_name(value):
    if not value:
        return None
    if isinstance(value, dict):
        return value.get("name")
    return str(value)


def _same_team(a, b):
    return bool(_team_name(a)) and _team_name(a) == _team_name(b)


def calculate_challenge_score(prediction: dict, results: dict):
    score = 0
    details = {
        "round32": 0,
        "round16": 0,
        "quarterFinals": 0,
        "semiFinals": 0,
        "champion": 0,
    }

    for round_key in ["round32", "round16", "quarterFinals", "semiFinals"]:
        pred_round = prediction.get(round_key, {}) or {}
        real_round = results.get(round_key, {}) or {}
        points = CHALLENGE_POINTS[round_key]

        for match_id, predicted_team in pred_round.items():
            real_team = real_round.get(match_id)
            if _same_team(predicted_team, real_team):
                score += points
                details[round_key] += points

    if _same_team(prediction.get("champion"), results.get("champion")):
        score += CHALLENGE_POINTS["champion"]
        details["champion"] += CHALLENGE_POINTS["champion"]

    return score, details


@api_router.post("/challenge/prediction")
async def save_challenge_prediction(data: ChallengePredictionIn, user=Depends(get_current_user)):
    status_info = challenge_lock_status()
    if status_info.get("locked"):
        raise HTTPException(
            status_code=403,
            detail="تم إغلاق توقع التحدي مع بداية أول مباراة في دور الـ32"
        )

    now = datetime.now(timezone.utc).isoformat()

    prediction = data.model_dump() if hasattr(data, "model_dump") else data.dict()

    doc = {
        "challenge_id": CHALLENGE_ID,
        "user_id": user["id"],
        "user_name": user.get("name"),
        "prediction": prediction,
        "updated_at": now,
    }

    await db.challenge_predictions.update_one(
        {
            "challenge_id": CHALLENGE_ID,
            "user_id": user["id"],
        },
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    return {
        "success": True,
        "message": "تم حفظ توقع التحدي",
        "prediction": prediction,
        "updated_at": now,
    }


@api_router.get("/challenge/my-prediction")
async def get_my_challenge_prediction(user=Depends(get_current_user)):
    doc = await db.challenge_predictions.find_one(
        {
            "challenge_id": CHALLENGE_ID,
            "user_id": user["id"],
        },
        {"_id": 0},
    )

    return {
        "prediction": doc.get("prediction") if doc else None,
        "updated_at": doc.get("updated_at") if doc else None,
    }


@api_router.put("/admin/challenge/results")
async def save_challenge_results(data: ChallengeResultsIn, _staff=Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()

    results = data.model_dump() if hasattr(data, "model_dump") else data.dict()

    doc = {
        "challenge_id": CHALLENGE_ID,
        "results": results,
        "updated_at": now,
    }

    await db.challenge_results.update_one(
        {"challenge_id": CHALLENGE_ID},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    return {
        "success": True,
        "message": "تم حفظ نتائج التحدي",
        "results": results,
        "updated_at": now,
    }


@api_router.get("/challenge/results")
async def get_challenge_results():
    doc = await db.challenge_results.find_one(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    )

    return {
        "results": doc.get("results") if doc else None,
        "updated_at": doc.get("updated_at") if doc else None,
    }


@api_router.get("/challenge/my-score")
async def get_my_challenge_score(user=Depends(get_current_user)):
    pred_doc = await db.challenge_predictions.find_one(
        {
            "challenge_id": CHALLENGE_ID,
            "user_id": user["id"],
        },
        {"_id": 0},
    )

    results_doc = await db.challenge_results.find_one(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    )

    if not pred_doc:
        return {
            "score": 0,
            "details": None,
            "has_prediction": False,
            "has_results": bool(results_doc),
        }

    if not results_doc:
        return {
            "score": 0,
            "details": None,
            "has_prediction": True,
            "has_results": False,
        }

    score, details = calculate_challenge_score(
        pred_doc.get("prediction", {}),
        results_doc.get("results", {}),
    )

    return {
        "score": score,
        "details": details,
        "has_prediction": True,
        "has_results": True,
    }


@api_router.get("/challenge/leaderboard")
async def get_challenge_leaderboard(limit: int = 50):
    results_doc = await db.challenge_results.find_one(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    )

    predictions = await db.challenge_predictions.find(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    ).to_list(10000)

    user_ids = [p.get("user_id") for p in predictions if p.get("user_id")]
    users_map = {}

    if user_ids:
        users = await db.users.find(
            {"id": {"$in": user_ids}},
            {"_id": 0, "id": 1, "name": 1, "avatar": 1, "role": 1},
        ).to_list(10000)

        users_map = {u["id"]: u for u in users}

    rows = []

    for pred in predictions:
        user_id = pred.get("user_id")
        user_doc = users_map.get(user_id, {})

        score = 0
        details = None

        if results_doc:
            score, details = calculate_challenge_score(
                pred.get("prediction", {}),
                results_doc.get("results", {}),
            )

        champion = (pred.get("prediction") or {}).get("champion") or {}

        rows.append({
            "user_id": user_id,
            "name": user_doc.get("name") or pred.get("user_name") or "مستخدم",
            "avatar": user_doc.get("avatar"),
            "role": user_doc.get("role", "user"),
            "score": score,
            "details": details,
            "champion": champion,
            "updated_at": pred.get("updated_at"),
        })

    rows.sort(key=lambda x: x.get("score", 0), reverse=True)

    for i, row in enumerate(rows, start=1):
        row["rank"] = i

    return {
        "has_results": bool(results_doc),
        "count": len(rows),
        "items": rows[:max(1, min(limit, 100))],
    }

# ===== End Challenge Predictions, Results, Scores API =====



# ===== Challenge Lock API =====

# وقت إغلاق توقع التحدي = بداية أول مباراة في دور الـ32
# الافتراضي: الإثنين 29 يونيو 2026 الساعة 23:30 مكة = 20:30 UTC
CHALLENGE_LOCK_AT = os.environ.get("CHALLENGE_LOCK_AT", "2026-06-29T20:30:00+00:00")


def _parse_challenge_lock_at():
    raw = CHALLENGE_LOCK_AT
    try:
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        # في حال كان التاريخ غير صحيح لا نكسر التطبيق، ونغلق حسب التاريخ الافتراضي
        return datetime(2026, 6, 29, 20, 30, tzinfo=timezone.utc)


def challenge_lock_status():
    lock_at = _parse_challenge_lock_at()
    now = datetime.now(timezone.utc)
    locked = now >= lock_at

    return {
        "locked": locked,
        "lock_at": lock_at.isoformat(),
        "server_time": now.isoformat(),
        "message": "توقع التحدي مغلق" if locked else "توقع التحدي مفتوح",
    }


@api_router.get("/challenge/status")
async def get_challenge_status():
    return challenge_lock_status()

# ===== End Challenge Lock API =====


@app.on_event("startup")
async def on_startup():
    # Indexes for faster login, matches, predictions, leaderboard, notifications and chat
    await db.users.create_index("email", unique=True)
    await db.users.create_index("role")
    await db.users.create_index([("role", 1), ("total_points", -1)])

    await db.matches.create_index("kickoff_utc")
    await db.matches.create_index("match_date")
    await db.matches.create_index("status")
    await db.matches.create_index([("match_date", 1), ("kickoff_utc", 1)])
    await db.matches.create_index([("home_team", 1), ("away_team", 1)])

    await db.predictions.create_index([("user_id", 1), ("match_id", 1)], unique=True)
    await db.predictions.create_index("user_id")
    await db.predictions.create_index("match_id")
    await db.predictions.create_index([("match_id", 1), ("points", 1)])

    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    await db.notifications.create_index([("user_id", 1), ("read", 1)])

    await db.chat_messages.create_index("created_at")

    await db.push_tokens.create_index("token", unique=True)
    await db.push_tokens.create_index("user_id")

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@malik-tawaqoat.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@2026")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one(
            {
                "id": str(uuid.uuid4()),
                "email": admin_email,
                "name": "المسؤول",
                "password_hash": hash_password(admin_password),
                "role": "admin",
                "total_points": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    else:
        if not verify_password(admin_password, existing["password_hash"]):
            await db.users.update_one(
                {"email": admin_email},
                {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}},
            )

    # Start background results auto-sync
    asyncio.create_task(auto_sync_loop())


@app.on_event("shutdown")
async def on_shutdown():
    client.close()



@api_router.get("/live-matches")
async def live_matches():
    now = datetime.now(timezone.utc)
    items = []

    cursor = db.matches.find({}).sort("kickoff", 1)
    async for m in cursor:
        kickoff_raw = m.get("kickoff") or m.get("kickoff_utc") or ""
        status_value = m.get("status", "scheduled")

        try:
            kickoff_dt = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00"))
        except Exception:
            kickoff_dt = None

        is_live = False
        minute = None

        if kickoff_dt:
            diff_min = int((now - kickoff_dt).total_seconds() / 60)
            if 0 <= diff_min <= 130 and status_value != "finished":
                is_live = True
                minute = max(1, min(diff_min, 120))

        if is_live or status_value in ["live", "in_progress", "finished"]:
            items.append({
                "id": m.get("id"),
                "home_team": m.get("home_team"),
                "away_team": m.get("away_team"),
                "home_score": m.get("home_score"),
                "away_score": m.get("away_score"),
                "kickoff": kickoff_raw,
                "status": "live" if is_live else status_value,
                "minute": minute,
                "stage": m.get("stage"),
                "group_name": m.get("group_name"),
            })

    return items



@api_router.post("/admin/seed-test-live")
async def seed_test_live(current_user=Depends(require_admin)):
    now = datetime.now(timezone.utc)
    kickoff = (now - timedelta(minutes=35)).isoformat()

    match = {
        "id": "test-arsenal-psg",
        "home_team": "arsenal",
        "away_team": "psg",
        "home_score": 1,
        "away_score": 1,
        "kickoff": kickoff,
        "match_date": now.date().isoformat(),
        "status": "live",
        "stage": "اختبار البث الحي",
        "group_name": "تجربة",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    await db.matches.update_one(
        {"id": "test-arsenal-psg"},
        {"$set": match},
        upsert=True
    )

    return {
        "success": True,
        "message": "تمت إضافة مباراة أرسنال وباريس للاختبار",
        "match": match
    }



@api_router.get("/external/live-matches")
async def external_live_matches():
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API_FOOTBALL_KEY غير موجود")

    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": api_key}

    async with httpx.AsyncClient(timeout=20) as client_http:
        r = await client_http.get(url, headers=headers, params={"live": "all"})
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)

        payload = r.json()

    ALLOWED_LIVE_LEAGUES = {
        "UEFA Champions League",
        "Premier League",
        "La Liga",
        "Bundesliga",
        "Ligue 1",
        "Saudi Pro League",
        "FIFA World Cup",
        "World Cup",
    }

    items = []
    for item in payload.get("response", []):
        fixture = item.get("fixture", {})
        league = item.get("league", {})

        if league.get("name") not in ALLOWED_LIVE_LEAGUES:
            continue
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        status = fixture.get("status", {})

        home = teams.get("home", {}) or {}
        away = teams.get("away", {}) or {}

        items.append({
            "id": fixture.get("id"),
            "league": league.get("name"),
            "country": league.get("country"),
            "league_logo": league.get("logo"),
            "home_team": team_ar_name(home.get("name")),
            "away_team": team_ar_name(away.get("name")),
            "home_logo": home.get("logo"),
            "away_logo": away.get("logo"),
            "home_score": goals.get("home"),
            "away_score": goals.get("away"),
            "elapsed": status.get("elapsed"),
            "status": status.get("short"),
            "status_long": status.get("long"),
            "date": fixture.get("date"),
        })

    return items



@api_router.post("/admin/import-new-fixtures")
async def import_new_fixtures(_admin=Depends(require_admin)):
    """
    يستورد مباريات كأس العالم الجديدة فقط من TheSportsDB
    بدون حذف أي مباراة أو توقع أو نقاط.
    """
    try:
        events = await fetch_world_cup_events()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"فشل جلب المباريات: {e}")

    created = 0
    skipped = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for ev in events:
        h_code = normalize_team_code(ev.get("strHomeTeam"))
        a_code = normalize_team_code(ev.get("strAwayTeam"))

        if not h_code or not a_code:
            skipped += 1
            continue

        existing = await db.matches.find_one({
            "$or": [
                {"home_team": h_code, "away_team": a_code},
                {"home_team": a_code, "away_team": h_code}
            ]
        })

        if existing:
            skipped += 1
            continue

        timestamp = ev.get("strTimestamp")
        date_event = ev.get("dateEvent")
        time_event = ev.get("strTime") or "00:00:00"

        try:
            if timestamp:
                kickoff = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elif date_event:
                kickoff = datetime.fromisoformat(f"{date_event}T{time_event}+00:00")
            else:
                kickoff = datetime.now(timezone.utc)
        except Exception:
            kickoff = datetime.now(timezone.utc)

        stage = ev.get("strRound") or ev.get("strStage") or "كأس العالم"

        doc = {
            "id": str(uuid.uuid4()),
            "home_team": h_code,
            "away_team": a_code,
            "match_date": kickoff.date().isoformat(),
            "kickoff_utc": kickoff.astimezone(timezone.utc).isoformat(),
            "stage": stage,
            "group_name": "",
            "status": "scheduled",
            "home_score": None,
            "away_score": None,
            "result_source": None,
            "result_updated_at": None,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        await db.matches.insert_one(doc)
        created += 1

    return {
        "success": True,
        "created": created,
        "skipped": skipped,
        "message": "تم استيراد مباريات كأس العالم الجديدة بدون حذف التوقعات"
    }



class ChatMessageIn(BaseModel):
    text: str

@api_router.get("/chat/messages")
async def get_chat_messages(_user=Depends(get_current_user)):
    rows = await db.chat_messages.find(
        {},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)

    return list(reversed(rows))

@api_router.post("/chat/messages")
async def send_chat_message(data: ChatMessageIn, user=Depends(get_current_user)):
    text = data.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="الرسالة فارغة")

    if len(text) > 300:
        raise HTTPException(status_code=400, detail="الرسالة طويلة جداً")

    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "user_name": user.get("name", "مستخدم"),
        "user_avatar": user.get("avatar"),
        "text": text,
        "created_at": now,
    }

    await db.chat_messages.insert_one(doc)

    return {
        "success": True,
        "message": doc
    }

@api_router.delete("/chat/messages/{message_id}")
async def delete_chat_message(message_id: str, staff=Depends(require_staff)):
    res = await db.chat_messages.delete_one({"id": message_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="الرسالة غير موجودة")

    return {"success": True}



class MatchTimeUpdate(BaseModel):
    kickoff: str

@api_router.patch("/admin/matches/{match_id}/time")
async def update_match_time(match_id: str, data: MatchTimeUpdate, _staff=Depends(require_staff)):
    match = await db.matches.find_one({"id": match_id}, {"_id": 0})
    if not match:
        raise HTTPException(status_code=404, detail="المباراة غير موجودة")

    await db.matches.update_one(
        {"id": match_id},
        {"$set": {"kickoff": data.kickoff}}
    )

    return {
        "success": True,
        "message": "تم تعديل وقت المباراة بدون حذف التوقعات",
        "kickoff": data.kickoff
    }

class MatchTimeByTeamsIn(BaseModel):
    home_team: str
    away_team: str
    kickoff: str

@api_router.patch("/admin/fix-match-time")
async def fix_match_time(data: MatchTimeByTeamsIn, _staff=Depends(require_staff)):
    match = await db.matches.find_one({
        "home_team": data.home_team,
        "away_team": data.away_team
    }, {"_id": 0})

    if not match:
        match = await db.matches.find_one({
            "home_team": data.away_team,
            "away_team": data.home_team
        }, {"_id": 0})

    if not match:
        raise HTTPException(status_code=404, detail="المباراة غير موجودة")

    await db.matches.update_one(
        {"id": match["id"]},
        {"$set": {"kickoff": data.kickoff}}
    )

    return {
        "success": True,
        "message": "تم تعديل وقت المباراة بدون حذف التوقعات",
        "match_id": match["id"],
        "kickoff": data.kickoff
    }



# ===== Challenge Bracket API =====

DEFAULT_CHALLENGE_ROUND32 = [
    {"id": "r32_1", "date": "الإثنين، 29 يونيو", "time": "23:30 مكة", "home": {"name": "كوت ديفوار", "flag": "🇨🇮"}, "away": {"name": "التشيك", "flag": "🇨🇿"}},
    {"id": "r32_2", "date": "الأربعاء، 1 يوليو", "time": "00:00 مكة", "home": {"name": "فرنسا", "flag": "🇫🇷"}, "away": {"name": "الرأس الأخضر", "flag": "🇨🇻"}},
    {"id": "r32_3", "date": "الأحد، 28 يونيو", "time": "22:00 مكة", "home": {"name": "كوريا الجنوبية", "flag": "🇰🇷"}, "away": {"name": "البوسنة", "flag": "🇧🇦"}},
    {"id": "r32_4", "date": "الثلاثاء، 30 يونيو", "time": "04:00 مكة", "home": {"name": "هولندا", "flag": "🇳🇱"}, "away": {"name": "البرازيل", "flag": "🇧🇷"}},
    {"id": "r32_5", "date": "الجمعة، 3 يوليو", "time": "02:00 مكة", "home": {"name": "أوزبكستان", "flag": "🇺🇿"}, "away": {"name": "كرواتيا", "flag": "🇭🇷"}},
    {"id": "r32_6", "date": "الخميس، 2 يوليو", "time": "22:00 مكة", "home": {"name": "إسبانيا", "flag": "🇪🇸"}, "away": {"name": "النمسا", "flag": "🇦🇹"}},
    {"id": "r32_7", "date": "الخميس، 2 يوليو", "time": "03:00 مكة", "home": {"name": "أستراليا", "flag": "🇦🇺"}, "away": {"name": "كندا", "flag": "🇨🇦"}},
    {"id": "r32_8", "date": "الأربعاء، 1 يوليو", "time": "23:00 مكة", "home": {"name": "المغرب", "flag": "🇲🇦"}, "away": {"name": "أمريكا", "flag": "🇺🇸"}},
    {"id": "r32_9", "date": "السبت، 4 يوليو", "time": "21:00 مكة", "home": {"name": "الأرجنتين", "flag": "🇦🇷"}, "away": {"name": "اليابان", "flag": "🇯🇵"}},
    {"id": "r32_10", "date": "الأحد، 5 يوليو", "time": "00:00 مكة", "home": {"name": "إنجلترا", "flag": "🏴"}, "away": {"name": "السنغال", "flag": "🇸🇳"}},
    {"id": "r32_11", "date": "الإثنين، 6 يوليو", "time": "22:00 مكة", "home": {"name": "ألمانيا", "flag": "🇩🇪"}, "away": {"name": "غانا", "flag": "🇬🇭"}},
    {"id": "r32_12", "date": "الثلاثاء، 7 يوليو", "time": "03:00 مكة", "home": {"name": "إيطاليا", "flag": "🇮🇹"}, "away": {"name": "مصر", "flag": "🇪🇬"}},
    {"id": "r32_13", "date": "الأربعاء، 8 يوليو", "time": "22:00 مكة", "home": {"name": "البرتغال", "flag": "🇵🇹"}, "away": {"name": "المكسيك", "flag": "🇲🇽"}},
    {"id": "r32_14", "date": "الخميس، 9 يوليو", "time": "23:00 مكة", "home": {"name": "أوروجواي", "flag": "🇺🇾"}, "away": {"name": "السعودية", "flag": "🇸🇦"}},
    {"id": "r32_15", "date": "الجمعة، 10 يوليو", "time": "22:00 مكة", "home": {"name": "بلجيكا", "flag": "🇧🇪"}, "away": {"name": "كولومبيا", "flag": "🇨🇴"}},
    {"id": "r32_16", "date": "السبت، 11 يوليو", "time": "00:00 مكة", "home": {"name": "سويسرا", "flag": "🇨🇭"}, "away": {"name": "الدنمارك", "flag": "🇩🇰"}},
]


class ChallengeTeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    flag: str = Field(min_length=1, max_length=12)


class ChallengeMatchIn(BaseModel):
    id: str
    date: str = Field(min_length=1, max_length=80)
    time: str = Field(min_length=1, max_length=80)
    home: ChallengeTeamIn
    away: ChallengeTeamIn


class ChallengeBracketIn(BaseModel):
    matches: List[ChallengeMatchIn]


@api_router.get("/challenge/bracket")
async def get_challenge_bracket():
    doc = await db.challenge_brackets.find_one(
        {"id": "worldcup2026_round32"},
        {"_id": 0}
    )

    if not doc:
        return {
            "id": "worldcup2026_round32",
            "matches": DEFAULT_CHALLENGE_ROUND32,
            "updated_at": None,
        }

    return doc


@api_router.put("/admin/challenge/bracket")
async def update_challenge_bracket(data: ChallengeBracketIn, _staff=Depends(require_staff)):
    if len(data.matches) != 16:
        raise HTTPException(status_code=400, detail="يجب أن يكون عدد مباريات دور الـ32 هو 16 مباراة")

    matches = []
    for m in data.matches:
        if hasattr(m, "model_dump"):
            matches.append(m.model_dump())
        else:
            matches.append(m.dict())

    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": "worldcup2026_round32",
        "matches": matches,
        "updated_at": now,
    }

    await db.challenge_brackets.update_one(
        {"id": "worldcup2026_round32"},
        {"$set": doc},
        upsert=True
    )

    return {"success": True, "updated_at": now, "matches": matches}

# ===== End Challenge Bracket API =====



# ===== Challenge Predictions, Results, Scores API =====

CHALLENGE_ID = "worldcup2026_round32"

CHALLENGE_POINTS = {
    "round32": 2,
    "round16": 4,
    "quarterFinals": 6,
    "semiFinals": 8,
    "champion": 15,
}


class ChallengePredictionIn(BaseModel):
    round32: dict = Field(default_factory=dict)
    round16: dict = Field(default_factory=dict)
    quarterFinals: dict = Field(default_factory=dict)
    semiFinals: dict = Field(default_factory=dict)
    final: dict = Field(default_factory=dict)
    champion: dict


class ChallengeResultsIn(BaseModel):
    round32: dict = Field(default_factory=dict)
    round16: dict = Field(default_factory=dict)
    quarterFinals: dict = Field(default_factory=dict)
    semiFinals: dict = Field(default_factory=dict)
    final: dict = Field(default_factory=dict)
    champion: dict


def _team_name(value):
    if not value:
        return None
    if isinstance(value, dict):
        return value.get("name")
    return str(value)


def _same_team(a, b):
    return bool(_team_name(a)) and _team_name(a) == _team_name(b)


def calculate_challenge_score(prediction: dict, results: dict):
    score = 0
    details = {
        "round32": 0,
        "round16": 0,
        "quarterFinals": 0,
        "semiFinals": 0,
        "champion": 0,
    }

    for round_key in ["round32", "round16", "quarterFinals", "semiFinals"]:
        pred_round = prediction.get(round_key, {}) or {}
        real_round = results.get(round_key, {}) or {}
        points = CHALLENGE_POINTS[round_key]

        for match_id, predicted_team in pred_round.items():
            real_team = real_round.get(match_id)
            if _same_team(predicted_team, real_team):
                score += points
                details[round_key] += points

    if _same_team(prediction.get("champion"), results.get("champion")):
        score += CHALLENGE_POINTS["champion"]
        details["champion"] += CHALLENGE_POINTS["champion"]

    return score, details


@api_router.post("/challenge/prediction")
async def save_challenge_prediction(data: ChallengePredictionIn, user=Depends(get_current_user)):
    status_info = challenge_lock_status()
    if status_info.get("locked"):
        raise HTTPException(
            status_code=403,
            detail="تم إغلاق توقع التحدي مع بداية أول مباراة في دور الـ32"
        )

    now = datetime.now(timezone.utc).isoformat()

    prediction = data.model_dump() if hasattr(data, "model_dump") else data.dict()

    doc = {
        "challenge_id": CHALLENGE_ID,
        "user_id": user["id"],
        "user_name": user.get("name"),
        "prediction": prediction,
        "updated_at": now,
    }

    await db.challenge_predictions.update_one(
        {
            "challenge_id": CHALLENGE_ID,
            "user_id": user["id"],
        },
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    return {
        "success": True,
        "message": "تم حفظ توقع التحدي",
        "prediction": prediction,
        "updated_at": now,
    }


@api_router.get("/challenge/my-prediction")
async def get_my_challenge_prediction(user=Depends(get_current_user)):
    doc = await db.challenge_predictions.find_one(
        {
            "challenge_id": CHALLENGE_ID,
            "user_id": user["id"],
        },
        {"_id": 0},
    )

    return {
        "prediction": doc.get("prediction") if doc else None,
        "updated_at": doc.get("updated_at") if doc else None,
    }


@api_router.put("/admin/challenge/results")
async def save_challenge_results(data: ChallengeResultsIn, _staff=Depends(require_staff)):
    now = datetime.now(timezone.utc).isoformat()

    results = data.model_dump() if hasattr(data, "model_dump") else data.dict()

    doc = {
        "challenge_id": CHALLENGE_ID,
        "results": results,
        "updated_at": now,
    }

    await db.challenge_results.update_one(
        {"challenge_id": CHALLENGE_ID},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    return {
        "success": True,
        "message": "تم حفظ نتائج التحدي",
        "results": results,
        "updated_at": now,
    }


@api_router.get("/challenge/results")
async def get_challenge_results():
    doc = await db.challenge_results.find_one(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    )

    return {
        "results": doc.get("results") if doc else None,
        "updated_at": doc.get("updated_at") if doc else None,
    }


@api_router.get("/challenge/my-score")
async def get_my_challenge_score(user=Depends(get_current_user)):
    pred_doc = await db.challenge_predictions.find_one(
        {
            "challenge_id": CHALLENGE_ID,
            "user_id": user["id"],
        },
        {"_id": 0},
    )

    results_doc = await db.challenge_results.find_one(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    )

    if not pred_doc:
        return {
            "score": 0,
            "details": None,
            "has_prediction": False,
            "has_results": bool(results_doc),
        }

    if not results_doc:
        return {
            "score": 0,
            "details": None,
            "has_prediction": True,
            "has_results": False,
        }

    score, details = calculate_challenge_score(
        pred_doc.get("prediction", {}),
        results_doc.get("results", {}),
    )

    return {
        "score": score,
        "details": details,
        "has_prediction": True,
        "has_results": True,
    }


@api_router.get("/challenge/leaderboard")
async def get_challenge_leaderboard(limit: int = 50):
    results_doc = await db.challenge_results.find_one(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    )

    predictions = await db.challenge_predictions.find(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    ).to_list(10000)

    user_ids = [p.get("user_id") for p in predictions if p.get("user_id")]
    users_map = {}

    if user_ids:
        users = await db.users.find(
            {"id": {"$in": user_ids}},
            {"_id": 0, "id": 1, "name": 1, "avatar": 1, "role": 1},
        ).to_list(10000)

        users_map = {u["id"]: u for u in users}

    rows = []

    for pred in predictions:
        user_id = pred.get("user_id")
        user_doc = users_map.get(user_id, {})

        score = 0
        details = None

        if results_doc:
            score, details = calculate_challenge_score(
                pred.get("prediction", {}),
                results_doc.get("results", {}),
            )

        champion = (pred.get("prediction") or {}).get("champion") or {}

        rows.append({
            "user_id": user_id,
            "name": user_doc.get("name") or pred.get("user_name") or "مستخدم",
            "avatar": user_doc.get("avatar"),
            "role": user_doc.get("role", "user"),
            "score": score,
            "details": details,
            "champion": champion,
            "updated_at": pred.get("updated_at"),
        })

    rows.sort(key=lambda x: x.get("score", 0), reverse=True)

    for i, row in enumerate(rows, start=1):
        row["rank"] = i

    return {
        "has_results": bool(results_doc),
        "count": len(rows),
        "items": rows[:max(1, min(limit, 100))],
    }

# ===== End Challenge Predictions, Results, Scores API =====



# ===== Challenge Lock API =====

# وقت إغلاق توقع التحدي = بداية أول مباراة في دور الـ32
# الافتراضي: الإثنين 29 يونيو 2026 الساعة 23:30 مكة = 20:30 UTC
CHALLENGE_LOCK_AT = os.environ.get("CHALLENGE_LOCK_AT", "2026-06-29T20:30:00+00:00")


def _parse_challenge_lock_at():
    raw = CHALLENGE_LOCK_AT
    try:
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        # في حال كان التاريخ غير صحيح لا نكسر التطبيق، ونغلق حسب التاريخ الافتراضي
        return datetime(2026, 6, 29, 20, 30, tzinfo=timezone.utc)


def challenge_lock_status():
    lock_at = _parse_challenge_lock_at()
    now = datetime.now(timezone.utc)
    locked = now >= lock_at

    return {
        "locked": locked,
        "lock_at": lock_at.isoformat(),
        "server_time": now.isoformat(),
        "message": "توقع التحدي مغلق" if locked else "توقع التحدي مفتوح",
    }


@api_router.get("/challenge/status")
async def get_challenge_status():
    return challenge_lock_status()

# ===== End Challenge Lock API =====


@app.on_event("startup")
async def start_auto_sync_results():
    asyncio.create_task(auto_sync_results_loop())
    asyncio.create_task(auto_match_reminders_loop())


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
