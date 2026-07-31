from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent

load_dotenv(ROOT_DIR / '.env')


import os


API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")
API_FOOTBALL_BASE_URL = os.environ.get(
    "API_FOOTBALL_BASE_URL",
    "https://v3.football.api-sports.io",
)
CURRENT_API_FOOTBALL_SEASON = 2026
import uuid
import logging
import bcrypt
import jwt
import re
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
import hashlib
import json
import httpx
import re
import unicodedata
from difflib import SequenceMatcher
import time

# Firebase Cloud Messaging
try:
    import firebase_admin
    from firebase_admin import credentials, messaging, auth as firebase_auth
except Exception:
    firebase_admin = None
    credentials = None
    messaging = None
    firebase_auth = None



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
    'Al Khaleej Saihat': 'الخليج',

    'Al Kholood': 'الخلود',

    'Al Okhdood': 'الأخدود',

    'Al Orubah': 'العروبة',

    'Al Riyadh': 'الرياض',

    'Al Shabab': 'الشباب',

    'Al Taawon': 'التعاون',

    'Al Wehda Club': 'الوحدة',

    'Al-Ettifaq': 'الاتفاق',

    'Al-Fateh': 'الفتح',

    'Al-Fayha': 'الفيحاء',

    'Al-Ittihad FC': 'الاتحاد',

    'Al-Qadisiyah FC': 'القادسية',

    'Al-Raed': 'الرائد',

    'Alaves': 'ألافيس',

    'Apoel Nicosia': 'أبويل نيقوسيا',

    'Athletic Club': 'أتلتيك بلباو',

    'Australia': 'أستراليا',

    'BSC Young Boys': 'يونغ بويز',

    'Ballkani': 'بالكاني',

    'Bayern München': 'بايرن ميونخ',

    'Belgium': 'بلجيكا',

    'Bodo/Glimt': 'بودو غليمت',

    'Bologna': 'بولونيا',

    'Borac Banja Luka': 'بوراك بانيا لوكا',

    'Bournemouth': 'بورنموث',

    'Brentford': 'برينتفورد',

    'Brighton': 'برايتون',

    'Cameroon': 'الكاميرون',

    'Canada': 'كندا',

    'Celje': 'تسيليه',

    'Celta Vigo': 'سيلتا فيغو',

    'Club Brugge KV': 'كلوب بروج',

    'Costa Rica': 'كوستاريكا',

    'Croatia': 'كرواتيا',

    'Crystal Palace': 'كريستال بالاس',

    'Damac': 'ضمك',

    'Denmark': 'الدنمارك',

    'Dečić': 'ديتشيتش',

    'Dinamo Batumi': 'دينامو باتومي',

    'Dinamo Minsk': 'دينامو مينسك',

    'Dinamo Zagreb': 'دينامو زغرب',

    'Dynamo Kyiv': 'دينامو كييف',

    'Ecuador': 'الإكوادور',

    'Egnatia Rrogozhinë': 'إغناتيا',

    'Espanyol': 'إسبانيول',

    'FC Differdange 03': 'ديفردانج 03',

    'FC Lugano': 'لوغانو',

    'FC Midtjylland': 'ميتييلاند',

    'FCSB': 'ستيوا بوخارست',

    'FK Crvena Zvezda': 'النجم الأحمر بلغراد',

    'FK Partizan': 'بارتيزان بلغراد',

    'Fenerbahçe': 'فنربخشة',

    'Ferencvarosi TC': 'فيرينتسفاروش',

    'Flora Tallinn': 'فلورا تالين',

    'Fulham': 'فولهام',

    'Getafe': 'خيتافي',

    'Ghana': 'غانا',

    'Girona': 'جيرونا',

    'HJK Helsinki': 'هلسنكي',

    'Hamrun Spartans': 'هامرون سبارتانز',

    'Ipswich': 'إيبسويتش تاون',

    'Iran': 'إيران',

    'Jagiellonia': 'ياغيلونيا',

    'KI Klaksvik': 'كلاكسفيك',

    'Larne': 'لارن',

    'Las Palmas': 'لاس بالماس',

    'Leganes': 'ليغانيس',

    'Lille': 'ليل',

    'Lincoln Red Imps FC': 'لينكولن ريد إمبس',

    'Ludogorets': 'لودوغوريتس',

    'Maccabi Tel Aviv': 'مكابي تل أبيب',

    'Mallorca': 'مايوركا',

    'Malmo FF': 'مالمو',

    'Mexico': 'المكسيك',

    'Monaco': 'موناكو',

    'Nottingham Forest': 'نوتنغهام فورست',

    'Ordabasy': 'أورداباسي',

    'Osasuna': 'أوساسونا',

    'PAOK': 'باوك',

    'Panevėžys': 'بانيفيجيس',

    'Petrocub': 'بيتروكوب',

    'Poland': 'بولندا',

    'Pyunik Yerevan': 'بيونيك يريفان',

    'Qarabag': 'قره باغ',

    'Qatar': 'قطر',

    'Rayo Vallecano': 'رايو فاييكانو',

    'Real Betis': 'ريال بيتيس',

    'Real Sociedad': 'ريال سوسيداد',

    'Red Bull Salzburg': 'ريد بول سالزبورغ',

    'Rīgas FS': 'ريغاس',

    'Senegal': 'السنغال',

    'Serbia': 'صربيا',

    'Shakhtar Donetsk': 'شاختار دونيتسك',

    'Shamrock Rovers': 'شامروك روفرز',

    'Slavia Praha': 'سلافيا براغ',

    'Slovan Bratislava': 'سلوفان براتيسلافا',

    'Southampton': 'ساوثهامبتون',

    'Sparta Praha': 'سبارتا براغ',

    'Stade Brestois 29': 'بريست',

    'Struga': 'ستروغا',

    'Sturm Graz': 'شتورم غراتس',

    'Switzerland': 'سويسرا',

    'The New Saints': 'ذا نيو سينتس',

    'Tunisia': 'تونس',

    'Twente': 'تفينتي',

    'UE Santa Coloma': 'سانتا كولوما',

    'Union St. Gilloise': 'سانت جيلواز',

    'Uruguay': 'الأوروغواي',

    'Valladolid': 'بلد الوليد',

    'VfB Stuttgart': 'شتوتغارت',

    'Vikingur Reykjavik': 'فيكينغور ريكيافيك',

    'Virtus': 'فيرتوس',

    'Wales': 'ويلز',

    'Wolves': 'وولفرهامبتون',


    "Deportivo Alavés": "ديبورتيفو ألافيس",

    "FC Barcelona": "برشلونة",
    "Real Madrid CF": "ريال مدريد",
    "Club Atlético de Madrid": "أتلتيكو مدريد",
    "Real Sociedad de Fútbol": "ريال سوسيداد",
    "Real Betis Balompié": "ريال بيتيس",
    "Valencia CF": "فالنسيا",
    "Villarreal CF": "فياريال",
    "RC Celta de Vigo": "سيلتا فيغو",
    "RCD Espanyol de Barcelona": "إسبانيول",
    "Athletic Club": "أتلتيك بلباو",
    "CA Osasuna": "أوساسونا",
    "Getafe CF": "خيتافي",
    "Sevilla FC": "إشبيلية",
    "Rayo Vallecano de Madrid": "رايو فاييكانو",
    "Real Racing Club de Santander": "راسينغ سانتاندير",
    "RC Deportivo La Coruña": "ديبورتيفو لاكورونيا",
    "Levante UD": "ليفانتي",
    "Elche CF": "إلتشي",
    "Málaga CF": "مالقا",

    "Getafe CF": "خيتافي",
    "Sevilla FC": "إشبيلية",
    "Rayo Vallecano de Madrid": "رايو فاييكانو",
    "Real Racing Club de Santander": "راسينغ سانتاندير",
    "Villarreal CF": "فياريال",
    "RCD Espanyol de Barcelona": "إسبانيول",
    "Levante UD": "ليفانتي",
    "RC Celta de Vigo": "سيلتا فيغو",
    "CA Osasuna": "أوساسونا",
    "RC Deportivo La Coruña": "ديبورتيفو لا كورونيا",
    "Elche CF": "إلتشي",
    "Club Atlético de Madrid": "أتلتيكو مدريد",
    "Málaga CF": "مالقة",
    "Real Betis Balompié": "ريال بيتيس",
    "Real Sociedad de Fútbol": "ريال سوسيداد",
    "Athletic Club": "أتلتيك بلباو",}

LEAGUE_AR_NAMES = {
    "Premier League": "الدوري الإنجليزي الممتاز",
    "La Liga": "الدوري الإسباني",
    "Primera División": "الدوري الإسباني",
    "Serie A": "الدوري الإيطالي",
    "Bundesliga": "الدوري الألماني",
    "Ligue 1": "الدوري الفرنسي",
    "UEFA Champions League": "دوري أبطال أوروبا",
    "UEFA Europa League": "الدوري الأوروبي",
    "UEFA Conference League": "دوري المؤتمر الأوروبي",
    "Saudi Pro League": "دوري روشن السعودي",
}




def team_ar_name(name):
    if not name:
        return name

    name = str(name).strip()

    aliases = [
        name,
        name.replace(" FC", ""),
        name.replace(" CF", ""),
        name.replace(" AFC", ""),
        name.replace(" AC", ""),
        name.replace(" SC", ""),
        name.replace(" UD", ""),
        name.replace(" CD", ""),
        name.replace(" Club", ""),
        name.replace(" Football Club", ""),
        name.replace(" Club Atlético de ", ""),
        name.replace(" Real ", ""),
        name.replace(" RC ", ""),
        name.replace(" RCD ", ""),
        name.replace(" CA ", ""),
    ]

    for alias in aliases:
        alias = alias.strip()
        if alias in TEAM_AR_NAMES:
            return TEAM_AR_NAMES[alias]

    return TEAM_AR_NAMES.get(name, name)


def league_ar_name(name: str | None):
    if not name:
        return name
    return LEAGUE_AR_NAMES.get(name, name)

def translate_round_ar(round_en: str | None) -> str | None:
    """Translate API-Football league.round to Arabic. Fallback to original."""
    if not round_en:
        return None
    s = str(round_en).strip()

    # Common finals
    low = s.lower()
    mapping = {
        "final": "النهائي",
        "semi-finals": "نصف النهائي",
        "semi final": "نصف النهائي",
        "quarter-finals": "ربع النهائي",
        "quarter final": "ربع النهائي",
        "round of 16": "دور الـ16",
        "round of 32": "دور الـ32",
        "3rd place final": "تحديد المركز الثالث",
        "third place": "تحديد المركز الثالث",
        "group stage": "مرحلة المجموعات",
        "play-offs": "ملحق",
        "playoffs": "ملحق",
    }
    for k, v in mapping.items():
        if low == k:
            return v

    # European qualifying rounds
    qualifying_mapping = {
        "preliminary round": "الدور التمهيدي",
        "1st qualifying round": "الدور التأهيلي الأول",
        "2nd qualifying round": "الدور التأهيلي الثاني",
        "3rd qualifying round": "الدور التأهيلي الثالث",
        "qualifying round": "الدور التأهيلي",
        "play-off round": "الدور الفاصل",
        "playoff round": "الدور الفاصل",
        "league stage": "مرحلة الدوري",
    }

    if low in qualifying_mapping:
        return qualifying_mapping[low]

    # League phase rounds
    m = re.search(r"(league stage|league phase)\s*-\s*(\d+)", low)
    if m:
        return f"مرحلة الدوري - الجولة {int(m.group(2))}"

    # Knockout phase
    m = re.search(r"(knockout round play-offs?)", low)
    if m:
        return "ملحق الأدوار الإقصائية"

    # Regular season rounds
    m = re.search(r"(regular season)\s*-\s*(\d+)", low)
    if m:
        return f"الجولة {int(m.group(2))}"

    # Championship Round / Relegation Round
    m = re.search(r"(championship round)\s*-\s*(\d+)", low)
    if m:
        return f"مرحلة البطولة - الجولة {int(m.group(2))}"
    m = re.search(r"(relegation round)\s*-\s*(\d+)", low)
    if m:
        return f"مرحلة الهبوط - الجولة {int(m.group(2))}"

    # Group Stage - Group A
    m = re.search(r"(group stage)\s*-\s*(group)\s*([a-z])", low)
    if m:
        return f"المجموعة {m.group(3).upper()}"

    # Week x
    m = re.search(r"(week)\s*(\d+)", low)
    if m:
        return f"الأسبوع {int(m.group(2))}"

    return s

def af_team_code(team_id: int | str | None) -> Optional[str]:
    if team_id is None:
        return None
    return f"af:{team_id}"

async def api_football_get(path: str, params: dict | None = None) -> dict:
    if not API_FOOTBALL_KEY:
        raise HTTPException(status_code=500, detail="API_FOOTBALL_KEY غير موجود")
    url = API_FOOTBALL_BASE_URL.rstrip("/") + "/" + path.lstrip("/")
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    async with httpx.AsyncClient(timeout=25) as client_http:
        r = await client_http.get(url, headers=headers, params=params or {})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"API-Football error {r.status_code}: {r.text[:400]}")
    data = r.json()
    errors = data.get("errors")
    # API sometimes returns errors as dict or list
    if isinstance(errors, dict) and errors:
        raise HTTPException(status_code=502, detail=f"API-Football errors: {errors}")
    if isinstance(errors, list) and errors:
        raise HTTPException(status_code=502, detail=f"API-Football errors: {errors}")
    return data

def _parse_dt(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        raw = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

MECCA_TZ = timezone(timedelta(hours=3))

API_CACHE_TTL_SECONDS = 1800  # 30 minutes

# حماية API-Football من الطلبات المتزامنة والمتكررة
_api_cache_locks = {}
_api_memory_cache = {}
_api_football_blocked_until = None
API_FOOTBALL_BLOCK_SECONDS = 21600  # 6 ساعات


async def cached_api_football_get(
    path: str,
    params: dict | None = None,
    ttl_seconds: int = API_CACHE_TTL_SECONDS,
):
    global _api_football_blocked_until

    params = params or {}

    key = hashlib.sha1(
        (
            path + "|" +
            json.dumps(params, sort_keys=True)
        ).encode()
    ).hexdigest()

    lock = _api_cache_locks.setdefault(
        key,
        asyncio.Lock()
    )

    async with lock:

        now = datetime.now(timezone.utc)

        memory = _api_memory_cache.get(key)

        if memory:
            age=(now-memory["updated"]).total_seconds()
            if age<ttl_seconds:
                return memory["data"]

        cached = await db.competition_cache.find_one(
            {"_id": key},
            {"_id": 0}
        )

        if cached and cached.get("data") is not None:

            try:
                updated = datetime.fromisoformat(
                    cached["updated_at"]
                )

                age = (
                    now - updated
                ).total_seconds()

                if age < ttl_seconds:

                    _api_memory_cache[key]={
                        "data":cached["data"],
                        "updated":updated,
                    }

                    return cached["data"]

            except Exception:
                pass

        # إذا API أوقف الحساب مؤقتًا لا نكرر ضربه
        if (
            _api_football_blocked_until
            and now < _api_football_blocked_until
        ):

            if cached and cached.get("data") is not None:

                logger.warning(
                    "API-Football blocked. Returning stale cache for %s",
                    path
                )

                return cached["data"]

            raise HTTPException(
                status_code=503,
                detail="بيانات البطولة غير متاحة مؤقتًا"
            )

        try:

            data = await api_football_get(
                path,
                params
            )

            await db.competition_cache.update_one(
                {"_id": key},
                {
                    "$set": {
                        "data": data,
                        "updated_at": now.isoformat()
                    }
                },
                upsert=True
            )

            _api_memory_cache[key]={
                "data":data,
                "updated":now,
            }

            return data

        except HTTPException as e:

            error_text = str(e.detail).lower()

            if (
                "suspended" in error_text
                or "ratelimit" in error_text
                or "too many requests" in error_text
                or "daily request limit" in error_text
            ):

                _api_football_blocked_until = (
                    now + timedelta(
                        seconds=API_FOOTBALL_BLOCK_SECONDS
                    )
                )

                logger.error(
                    "API-Football temporarily blocked until %s: %s",
                    _api_football_blocked_until.isoformat(),
                    e.detail
                )

            if cached and cached.get("data") is not None:

                logger.warning(
                    "API-Football unavailable for %s. Returning stale cache. Error: %s",
                    path,
                    e.detail
                )

                return cached["data"]

            raise


async def upsert_api_football_team(team: dict):
    """team object from API-Football: {id, name, logo, winner?}"""
    if not team:
        return
    tid = team.get("id")
    name_en = team.get("name")
    if not tid or not name_en:
        return

    code = af_team_code(tid)
    doc = {
        "code": code,
        "name_en": str(name_en),
        "name_ar": team_ar_name(str(name_en)),
        "confederation": "club",
        "type": "club",
        "api_football_team_id": int(tid),
        "logo": team.get("logo"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.football_teams.update_one(
        {"code": code},
        {"$set": doc, "$setOnInsert": {"created_at": doc["updated_at"]}},
        upsert=True,
    )

def simplify_league_row(item: dict) -> dict:
    league = item.get("league") or {}
    country = item.get("country") or {}
    seasons = item.get("seasons") or []
    years = [s.get("year") for s in seasons if s.get("year")]
    current = next((s.get("year") for s in seasons if s.get("current") and s.get("year")), None)
    return {
        "id": league.get("id"),
        "name_en": league.get("name"),
        "name_ar": league_ar_name(league.get("name")),
        "type": league.get("type"),
        "logo": league.get("logo"),
        "country": country.get("name"),
        "country_code": country.get("code"),
        "country_flag": country.get("flag"),
        "seasons": years,
        "current_season": current or (max(years) if years else None),
    }

def simplify_fixture(item: dict) -> dict:
    fixture = item.get("fixture") or {}
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    status = fixture.get("status") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}

    league_name_en = league.get("name")
    league_name_ar = league_ar_name(league_name_en)
    round_en = league.get("round")
    round_ar = translate_round_ar(round_en)

    return {
        "fixture_id": fixture.get("id"),
        "kickoff_utc": fixture.get("date"),
        "timestamp": fixture.get("timestamp"),
        "status": {
            "short": status.get("short"),
            "long": status.get("long"),
            "elapsed": status.get("elapsed"),
        },
        "league": {
            "id": league.get("id"),
            "name_en": league_name_en,
            "name_ar": league_name_ar,
            "logo": league.get("logo"),
            "country": league.get("country"),
            "season": league.get("season"),
            "round_en": round_en,
            "round_ar": round_ar,
        },
        "teams": {
            "home": {
                "id": home.get("id"),
                "name_en": home.get("name"),
                "name_ar": team_ar_name(home.get("name")),
                "logo": home.get("logo"),
            },
            "away": {
                "id": away.get("id"),
                "name_en": away.get("name"),
                "name_ar": team_ar_name(away.get("name")),
                "logo": away.get("logo"),
            },
        },
        "goals": {
            "home": goals.get("home"),
            "away": goals.get("away"),
        }
    }



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


class GoogleAuthIn(BaseModel):
    id_token: str = Field(min_length=20)


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
    # إضافات اختيارية (لا تكسر الواجهة الحالية)
    logo: Optional[str] = None
    type: Optional[str] = None
    api_football_team_id: Optional[int] = None


class MatchCreate(BaseModel):
    home_team: str  # team code
    away_team: str
    match_date: str  # ISO date string YYYY-MM-DD
    kickoff: str  # ISO datetime UTC
    competition: Optional[str] = None
    stage: str = "مرحلة المجموعات"
    group_name: Optional[str] = None


class MatchUpdate(BaseModel):
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    match_date: Optional[str] = None
    kickoff: Optional[str] = None
    competition: Optional[str] = None
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
    competition: Optional[str] = None
    stage: str
    group_name: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: Literal["scheduled", "finished"] = "scheduled"
    result_updated_at: Optional[str] = None
    result_source: Optional[str] = None
    # إضافات اختيارية لمباريات API-Football
    external_provider: Optional[str] = None
    external_fixture_id: Optional[int] = None
    league_id: Optional[int] = None
    league_name_en: Optional[str] = None
    league_name_ar: Optional[str] = None
    league_logo: Optional[str] = None
    season: Optional[int] = None
    round_en: Optional[str] = None
    round_ar: Optional[str] = None


class PredictionIn(BaseModel):
    match_id: str
    home_score: int = Field(ge=0, le=30)
    away_score: int = Field(ge=0, le=30)


class CompetitionPredictionIn(BaseModel):
    fixture_id: str
    external_provider: Literal["football_data"] = "football_data"

    home_team: str
    away_team: str

    kickoff: str
    match_date: str

    competition: str = "football_data"

    league_id: Optional[int] = None
    league_name_en: Optional[str] = None
    league_name_ar: Optional[str] = None

    home_score: int = Field(ge=0, le=30)
    away_score: int = Field(ge=0, le=30)



class CompetitionPredictionStats(BaseModel):
    total_predictions: int

    home_win_count: int
    draw_count: int
    away_win_count: int

    home_win_percent: int
    draw_percent: int
    away_win_percent: int

    same_score_count: int
    same_score_percent: int


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


@api_router.post("/auth/google", response_model=AuthOut)
async def google_login(data: GoogleAuthIn):
    if firebase_admin is None or firebase_auth is None:
        raise HTTPException(
            status_code=503,
            detail="تسجيل الدخول بواسطة Google غير متاح حالياً",
        )

    try:
        if not firebase_admin._apps:
            service_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

            if service_json:
                cred = credentials.Certificate(json.loads(service_json))
                firebase_admin.initialize_app(cred)
            else:
                key_path = ROOT_DIR / "serviceAccountKey.json"

                if not key_path.exists():
                    raise HTTPException(
                        status_code=500,
                        detail="serviceAccountKey.json not found",
                    )

                cred = credentials.Certificate(str(key_path))
                firebase_admin.initialize_app(cred)

        decoded = firebase_auth.verify_id_token(
            data.id_token,
            check_revoked=False,
        )
    except Exception as exc:
        import traceback

        logger.error(
            "GOOGLE VERIFY ERROR: %r",
            exc,
        )

        logger.error(traceback.format_exc())

        raise HTTPException(
            status_code=401,
            detail=str(exc),
        )

    email = str(decoded.get("email") or "").lower().strip()
    name = str(decoded.get("name") or "").strip()
    picture = str(decoded.get("picture") or "").strip()
    firebase_uid = str(decoded.get("uid") or decoded.get("sub") or "").strip()
    email_verified = bool(decoded.get("email_verified"))

    if not email or not firebase_uid:
        raise HTTPException(
            status_code=401,
            detail="حساب Google لا يحتوي على بيانات دخول صالحة",
        )

    if not email_verified:
        raise HTTPException(
            status_code=401,
            detail="البريد الإلكتروني في حساب Google غير موثّق",
        )

    user = await db.users.find_one({"email": email})

    if user:
        updates = {
            "google_uid": firebase_uid,
            "auth_provider": "google",
        }

        if picture and not user.get("avatar"):
            updates["avatar"] = picture

        await db.users.update_one(
            {"id": user["id"]},
            {"$set": updates},
        )

        user = {
            **user,
            **updates,
        }

    else:
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        user = {
            "id": user_id,
            "email": email,
            "name": name or email.split("@", 1)[0],
            "role": "user",
            "total_points": 0,
            "avatar": picture or None,
            "google_uid": firebase_uid,
            "auth_provider": "google",
            "created_at": now,
        }

        await db.users.insert_one(user)

    token = create_token(user["id"])

    return {
        "user": user_to_public(user),
        "token": token,
    }


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
    """
    فرق كأس العالم + football_teams + جميع فرق البطولات المخزنة.
    """
    merged = []
    seen_codes = set()

    def add_team(team):
        code = team.get("code")

        if not code or code in seen_codes:
            return

        merged.append({
            "code": code,
            "name_ar": team.get("name_ar") or team_ar_name(
                team.get("name_en") or team.get("name")
            ),
            "name_en": team.get("name_en") or team.get("name") or code,
            "confederation": team.get("confederation") or "API-Football",
            "logo": team.get("logo"),
            "type": team.get("type") or "club",
            "api_football_team_id": team.get("api_football_team_id"),
        })

        seen_codes.add(code)

    for team in WORLD_CUP_TEAMS:
        add_team(team)

    # فرق البطولات أولاً حتى تكون الترجمة والشعارات هي المعتمدة
    competition_docs = await db.competition_data.find(
        {"kind": "teams"},
        {"_id": 0, "items": 1},
    ).to_list(1000)

    for doc in competition_docs:
        for team in doc.get("items") or []:
            team_id = team.get("id")

            if not team_id:
                continue

            add_team({
                "code": af_team_code(team_id),
                "name_ar": team_ar_name(
                    team.get("name_en") or team.get("name")
                ),
                "name_en": team.get("name_en") or team.get("name"),
                "confederation": "API-Football",
                "logo": team.get("logo"),
                "type": "club",
                "api_football_team_id": int(team_id),
            })

    # football_teams تكمل أي فرق غير موجودة في بيانات البطولات
    extra_teams = await db.football_teams.find(
        {},
        {"_id": 0},
    ).to_list(50000)

    for team in extra_teams:
        add_team(team)

    merged.sort(
        key=lambda team: (
            team.get("name_ar") or team.get("name_en") or ""
        )
    )

    return merged


# ---------- Matches ----------
@api_router.get("/matches", response_model=List[MatchModel])
async def list_matches(date: Optional[str] = None):
    query = {
        "competition": {
            "$ne": "worldcup"
        }
    }

    if date:
        query["match_date"] = date

    rows = await db.matches.find(
        {
            "$or": [
                {"competition": {"$exists": False}},
                {"competition": None},
                {"competition": {"$nin": ["worldcup", "world_cup"]}}
            ],
            **({"match_date": date} if date else {})
        },
        {"_id": 0}
    ).sort("kickoff", 1).to_list(1000)

    print("QUERY_ROWS =", len(rows))
    print("FIRST_ROWS =", [
        (m.get("competition"), m.get("home_team"), m.get("away_team"))
        for m in rows[:10]
    ])


    # إخفاء مباريات كأس العالم من تبويب المباريات
    rows = [
        m for m in rows
        if "worldcup" not in str(m.get("competition", "")).lower()
    ]

    def norm(team):
        if not team:
            return ""
        t = str(team).strip().lower()
        mapping = {
            "spain": "es",
            "argentina": "ar",
            "france": "fr",
            "england": "gb-eng",
            "brazil": "br",
            "germany": "de",
            "portugal": "pt",
            "netherlands": "nl",
            "belgium": "be",
            "mexico": "mx",
            "united states": "us",
            "usa": "us",
            "canada": "ca",
            "morocco": "ma",
            "japan": "jp",
            "croatia": "hr",
            "switzerland": "ch",
            "colombia": "co",
            "norway": "no",
            "paraguay": "py",
            "austria": "at",
        }
        return mapping.get(t, t)

    result = []
    manual_keys = set()

    # أضف المباريات اليدوية أولاً
    for m in rows:
        if m.get("external_provider"):
            continue

        key = (
            norm(m.get("home_team")),
            norm(m.get("away_team")),
            str(m.get("match_date"))[:10],
        )

        manual_keys.add(key)
        result.append(m)

    # أضف الخارجية إذا لم توجد نسخة يدوية
    for m in rows:
        if not m.get("external_provider"):
            continue

        key = (
            norm(m.get("home_team")),
            norm(m.get("away_team")),
            str(m.get("match_date"))[:10],
        )

        if key in manual_keys:
            continue

        result.append(m)

    # إخفاء جميع المباريات اليدوية (التي لا تملك league_id)
    result = [
        m for m in result
        if m.get("league_id") is not None
    ]

    return result


@api_router.post("/matches", response_model=MatchModel)
async def create_match(data: MatchCreate, _staff=Depends(require_staff)):
    if data.home_team == data.away_team:
        raise HTTPException(status_code=400, detail="لا يمكن أن يكون الفريقان متطابقين")
    # السماح بجميع الفرق التي يعرضها /teams للإدارة
    available_teams = await get_teams()

    codes = {
        team.code
        for team in available_teams
        if team.code
    }

    if data.home_team not in codes:
        raise HTTPException(
            status_code=400,
            detail=f"رمز الفريق الأول غير صالح: {data.home_team}"
        )

    if data.away_team not in codes:
        raise HTTPException(
            status_code=400,
            detail=f"رمز الفريق الثاني غير صالح: {data.away_team}"
        )
    match = {
        "id": str(uuid.uuid4()),
        "home_team": data.home_team,
        "away_team": data.away_team,
        "match_date": data.match_date,
        "kickoff": data.kickoff,
        # keep legacy compatibility
        "kickoff_utc": data.kickoff,
        "competition": data.competition,
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
    # keep legacy compatibility: update kickoff_utc whenever kickoff updated
    if "kickoff" in updates and "kickoff_utc" not in updates:
        updates["kickoff_utc"] = updates["kickoff"]
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



async def ensure_competition_match(data: CompetitionPredictionIn):
    existing = await db.matches.find_one(
        {
            "external_provider": data.external_provider,
            "external_fixture_id": int(str(data.fixture_id).replace("fd:", "")),
        },
        {"_id": 0},
    )

    if existing:
        return existing

    match = {
        "id": str(uuid.uuid4()),
        "home_team": data.home_team,
        "away_team": data.away_team,
        "match_date": data.match_date,
        "kickoff": data.kickoff,
        "competition": data.competition,
        "stage": "",
        "group_name": None,
        "home_score": None,
        "away_score": None,
        "status": "scheduled",
        "external_provider": data.external_provider,
        "external_fixture_id": int(str(data.fixture_id).replace("fd:", "")),
        "league_id": data.league_id,
        "league_name_en": data.league_name_en,
        "league_name_ar": data.league_name_ar,
    }

    await db.matches.insert_one(match.copy())

    return match



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

@api_router.post("/competition/predictions", response_model=PredictionModel)
async def submit_competition_prediction(
    data: CompetitionPredictionIn,
    user=Depends(get_current_user),
):
    match = await ensure_competition_match(data)

    prediction = PredictionIn(
        match_id=match["id"],
        home_score=data.home_score,
        away_score=data.away_score,
    )

    return await submit_prediction(prediction, user)




@api_router.get(
    "/competition/predictions/stats/{fixture_id}",
    response_model=CompetitionPredictionStats,
)
async def competition_prediction_stats(
    fixture_id: str,
    home_score: int | None = None,
    away_score: int | None = None,
):
    fixture = int(str(fixture_id).replace("fd:", ""))

    match = await db.matches.find_one(
        {
            "external_fixture_id": fixture
        },
        {"_id": 0},
    )

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    predictions = await db.predictions.find(
        {
            "match_id": match["id"]
        },
        {"_id": 0},
    ).to_list(50000)

    total = len(predictions)

    if total == 0:
        return CompetitionPredictionStats(
            total_predictions=0,
            home_win_count=0,
            draw_count=0,
            away_win_count=0,
            home_win_percent=0,
            draw_percent=0,
            away_win_percent=0,
            same_score_count=0,
            same_score_percent=0,
        )

    home = 0
    draw = 0
    away = 0
    exact = 0

    for p in predictions:

        hs = p["home_score"]
        aw = p["away_score"]

        if hs > aw:
            home += 1
        elif hs < aw:
            away += 1
        else:
            draw += 1

        if (
            home_score is not None
            and away_score is not None
            and hs == home_score
            and aw == away_score
        ):
            exact += 1

    return CompetitionPredictionStats(
        total_predictions=total,

        home_win_count=home,
        draw_count=draw,
        away_win_count=away,

        home_win_percent=round(home * 100 / total),
        draw_percent=round(draw * 100 / total),
        away_win_percent=round(away * 100 / total),

        same_score_count=exact,
        same_score_percent=round(exact * 100 / total),
    )


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

    total = await db.predictions.count_documents(query)

    preds = await db.predictions.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).to_list(5000)

    # Build user + match lookup tables to enrich
    user_ids = list({p["user_id"] for p in preds})
    match_ids = list({p["match_id"] for p in preds})
    users = await db.users.find(
        {"id": {"$in": user_ids}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "avatar": 1, "role": 1},
    ).to_list(10000) if user_ids else []
    matches = await db.matches.find(
        {"id": {"$in": match_ids}},
        {"_id": 0, "id": 1, "home_team": 1, "away_team": 1, "kickoff_utc": 1, "kickoff": 1,
         "status": 1, "home_score": 1, "away_score": 1, "group": 1, "stage": 1, "group_name": 1},
    ).to_list(10000) if match_ids else []
    umap = {u["id"]: u for u in users}
    mmap = {m["id"]: m for m in matches}

    rows = []
    for p in preds:
        u = umap.get(p["user_id"], {})
        m = mmap.get(p["match_id"], {})
        kickoff_val = m.get("kickoff_utc") or m.get("kickoff")
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
                "kickoff_utc": kickoff_val,
                "status": m.get("status"),
                "home_score": m.get("home_score"),
                "away_score": m.get("away_score"),
                "group": m.get("group"),
                "stage": m.get("stage"),
                "group_name": m.get("group_name"),
            } if m else None,
        })
    return {"count": total, "items": rows}




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

    # مزامنة مجموع النقاط الحقيقي لكل مستخدم
    affected_users = {pred["user_id"] for pred in predictions}

    for user_id in affected_users:
        agg = await db.predictions.aggregate([
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$points", 0]}}}}
        ]).to_list(1)

        total = agg[0]["total"] if agg else 0

        await db.users.update_one(
            {"id": user_id},
            {"$set": {"total_points": total}}
        )

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


# ===============================
# API-Football Admin Endpoints
# ===============================
class AFImportFixturesIn(BaseModel):
    league_id: int
    season: int
    round: Optional[str] = None  # API-Football expects round in English as returned by /fixtures/rounds
    from_date: Optional[str] = None  # YYYY-MM-DD
    to_date: Optional[str] = None    # YYYY-MM-DD


@api_router.get("/admin/api-football/leagues")
async def admin_api_football_leagues(search: Optional[str] = None, _staff=Depends(require_staff)):
    params = {}
    if search:
        params["search"] = search
    data = await cached_api_football_get("/leagues", params)
    items = [simplify_league_row(x) for x in (data.get("response") or [])]
    return {"count": len(items), "items": items}


@api_router.get("/admin/api-football/seasons")
async def admin_api_football_seasons(league_id: int, _staff=Depends(require_staff)):
    data = await cached_api_football_get("/leagues", {"id": league_id})
    resp = (data.get("response") or [])
    if not resp:
        return {"league_id": league_id, "seasons": [], "current_season": None}
    row = simplify_league_row(resp[0])
    return {"league_id": league_id, "seasons": row.get("seasons") or [], "current_season": row.get("current_season")}


@api_router.get("/admin/api-football/rounds")
async def admin_api_football_rounds(league_id: int, season: int, _staff=Depends(require_staff)):
    data = await cached_api_football_get("/fixtures/rounds", {"league": league_id, "season": season})
    rounds = data.get("response") or []
    items = [{"round_en": r, "round_ar": translate_round_ar(r)} for r in rounds]
    return {"count": len(items), "items": items}


@api_router.post("/admin/api-football/import-fixtures")
async def admin_api_football_import_fixtures(data: AFImportFixturesIn, _staff=Depends(require_staff)):
    """Import fixtures from API-Football into db.matches WITHOUT deleting any predictions."""
    from pymongo import UpdateOne

    logger.info("IMPORT START")
    sync_start = datetime.now(timezone.utc).isoformat()

    params = {"league": data.league_id, "season": data.season}
    if data.round:
        params["round"] = data.round
    if data.from_date:
        params["from"] = data.from_date
    if data.to_date:
        params["to"] = data.to_date

    payload = await api_football_get("/fixtures", params)
    fixtures = payload.get("response") or []

    created = 0
    updated = 0
    skipped = 0
    finished_applied = 0
    teams_upserted = 0

    now_iso = datetime.now(timezone.utc).isoformat()

    # تحميل جميع مباريات API-Football الحالية مرة واحدة قبل الحلقة
    existing_matches_by_fixture_id: dict[int, dict] = {}
    cursor_matches = db.matches.find(
        {"external_provider": "api_football", "external_fixture_id": {"$exists": True}},
        {"_id": 0, "id": 1, "external_fixture_id": 1, "status": 1, "home_score": 1, "away_score": 1},
    )
    async for m in cursor_matches:
        try:
            fid = int(m.get("external_fixture_id"))
        except Exception:
            continue
        existing_matches_by_fixture_id[fid] = m

    # تحميل جميع football_teams مرة واحدة قبل الحلقة (مع الحقول المطلوبة فقط)
    existing_teams_by_code: dict[str, dict] = {}
    cursor_teams = db.football_teams.find(
        {},
        {"_id": 0, "code": 1, "name_en": 1, "name_ar": 1, "logo": 1, "api_football_team_id": 1, "updated_at": 1},
    )
    async for t in cursor_teams:
        code = t.get("code")
        if code:
            existing_teams_by_code[str(code)] = t

    # إنشاء match_ops و team_ops قبل الحلقة
    match_ops: list[UpdateOne] = []
    team_ops_by_code: dict[str, UpdateOne] = {}

    # قائمة النتائج المنتهية لتطبيق apply_match_result بعد انتهاء bulk_write فقط
    finished_to_apply: list[tuple[str, int, int]] = []  # (match_id, home_goals, away_goals)

    seen_fixture_ids: set[int] = set()

    # عدم تنفيذ أي عملية MongoDB داخل الحلقة
    for item in fixtures:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        goals = item.get("goals") or {}
        status_short = (fixture.get("status") or {}).get("short")

        fixture_id = fixture.get("id")
        if not fixture_id:
            skipped += 1
            continue

        try:
            fixture_id_int = int(fixture_id)
        except Exception:
            skipped += 1
            continue

        # منع العمليات المكررة لنفس المباراة داخل نفس الاستيراد
        if fixture_id_int in seen_fixture_ids:
            skipped += 1
            continue
        seen_fixture_ids.add(fixture_id_int)

        kickoff_dt = _parse_dt(fixture.get("date"))
        if not kickoff_dt:
            skipped += 1
            continue

        home = teams.get("home") or {}
        away = teams.get("away") or {}

        home_id = home.get("id")
        away_id = away.get("id")

        if home_id is None or away_id is None:
            skipped += 1
            continue

        home_code = af_team_code(home_id)
        away_code = af_team_code(away_id)
        if not home_code or not away_code:
            skipped += 1
            continue

        # upsert teams (bulk) - مع مقارنة القيم لتجنب تحديث غير ضروري
        if home.get("id"):
            teams_upserted += 1
        if away.get("id"):
            teams_upserted += 1

        # Home team bulk op
        try:
            hid_int = int(home_id)
        except Exception:
            hid_int = None
        if hid_int is not None and home.get("name"):
            new_doc = {
                "code": home_code,
                "name_en": str(home.get("name")),
                "name_ar": team_ar_name(str(home.get("name"))),
                "confederation": "club",
                "type": "club",
                "api_football_team_id": int(hid_int),
                "logo": home.get("logo"),
                "updated_at": now_iso,
            }

            old = existing_teams_by_code.get(home_code)
            old_changed = True
            if old:
                old_changed = any([
                    old.get("name_en") != new_doc.get("name_en"),
                    old.get("name_ar") != new_doc.get("name_ar"),
                    old.get("logo") != new_doc.get("logo"),
                    old.get("api_football_team_id") != new_doc.get("api_football_team_id"),
                ])

            if (not old) or old_changed:
                team_ops_by_code[home_code] = UpdateOne(
                    {"code": home_code},
                    {"$set": new_doc, "$setOnInsert": {"created_at": now_iso}},
                    upsert=True,
                )

        # Away team bulk op
        try:
            aid_int = int(away_id)
        except Exception:
            aid_int = None
        if aid_int is not None and away.get("name"):
            new_doc = {
                "code": away_code,
                "name_en": str(away.get("name")),
                "name_ar": team_ar_name(str(away.get("name"))),
                "confederation": "club",
                "type": "club",
                "api_football_team_id": int(aid_int),
                "logo": away.get("logo"),
                "updated_at": now_iso,
            }

            old = existing_teams_by_code.get(away_code)
            old_changed = True
            if old:
                old_changed = any([
                    old.get("name_en") != new_doc.get("name_en"),
                    old.get("name_ar") != new_doc.get("name_ar"),
                    old.get("logo") != new_doc.get("logo"),
                    old.get("api_football_team_id") != new_doc.get("api_football_team_id"),
                ])

            if (not old) or old_changed:
                team_ops_by_code[away_code] = UpdateOne(
                    {"code": away_code},
                    {"$set": new_doc, "$setOnInsert": {"created_at": now_iso}},
                    upsert=True,
                )

        kickoff_utc_iso = kickoff_dt.isoformat().replace("+00:00", "Z")
        match_date_mecca = kickoff_dt.astimezone(MECCA_TZ).date().isoformat()

        league_name_en = league.get("name")
        league_name_ar = league_ar_name(league_name_en)
        round_en = league.get("round")
        round_ar = translate_round_ar(round_en)

        base_doc = {
            "home_team": home_code,
            "away_team": away_code,
            "match_date": match_date_mecca,
            "kickoff": kickoff_utc_iso,
            "kickoff_utc": kickoff_utc_iso,  # legacy compatibility
            "competition": f"api_football:{data.league_id}",
            "stage": league_name_ar or (league_name_en or "بطولة"),
            "group_name": round_ar,
            "status": "scheduled",
            "home_score": None,
            "away_score": None,
            "external_provider": "api_football",
            "external_fixture_id": int(fixture_id_int),
            "league_id": int(league.get("id") or data.league_id),
            "league_name_en": league_name_en,
            "league_name_ar": league_name_ar,
            "league_logo": league.get("logo"),
            "season": int(league.get("season") or data.season),
            "round_en": round_en,
            "round_ar": round_ar,
            "updated_at": now_iso,
        }

        existing = existing_matches_by_fixture_id.get(fixture_id_int)
        if existing:
            updated += 1
            match_id = existing["id"]
            existing_finished = existing.get("status") == "finished"
        else:
            created += 1
            match_id = str(uuid.uuid4())
            existing_finished = False

        # إذا كانت المباراة موجودة وحالتها finished فلا تعد حالتها إلى scheduled ولا تمس home_score أو away_score
        set_doc = dict(base_doc)
        if existing_finished:
            set_doc.pop("status", None)
            set_doc.pop("home_score", None)
            set_doc.pop("away_score", None)

        match_ops.append(
            UpdateOne(
                {"external_fixture_id": int(fixture_id_int)},
                {
                    "$set": set_doc,
                    "$setOnInsert": {
                        "id": match_id,
                        "created_at": now_iso,
                    },
                },
                upsert=True,
            )
        )

        # تجميع النتائج المنتهية لتطبيقها بعد انتهاء bulk_write فقط
        if (not existing_finished) and (status_short in API_FOOTBALL_FINISHED_SHORT):
            h = goals.get("home")
            a = goals.get("away")
            if isinstance(h, int) and isinstance(a, int):
                finished_to_apply.append((match_id, int(h), int(a)))

    logger.info("IMPORT BULK MATCHES")
    try:
        if match_ops:
            await db.matches.bulk_write(match_ops, ordered=False)
    except Exception as e:
        logger.error(f"IMPORT BULK MATCHES ERROR: {e}")
        raise

    logger.info("IMPORT BULK TEAMS")
    try:
        team_ops = list(team_ops_by_code.values())
        if team_ops:
            await db.football_teams.bulk_write(team_ops, ordered=False)
    except Exception as e:
        logger.error(f"IMPORT BULK TEAMS ERROR: {e}")
        raise

    logger.info("IMPORT APPLY RESULTS")
    applied_match_ids: list[str] = []
    for match_id, h, a in finished_to_apply:
        try:
            await apply_match_result(match_id, int(h), int(a), source="auto")
            finished_applied += 1
            applied_match_ids.append(match_id)
        except Exception:
            pass

    # بعد apply_match_result حدث result_provider = api_football باستخدام Bulk أيضاً
    if applied_match_ids:
        try:
            await db.matches.bulk_write(
                [UpdateOne({"id": mid}, {"$set": {"result_provider": "api_football"}}) for mid in applied_match_ids],
                ordered=False,
            )
        except Exception as e:
            logger.error(f"IMPORT RESULT_PROVIDER BULK ERROR: {e}")

    await db.app_state.update_one(
        {"key": "last_sync_api_football"},
        {"$set": {"key": "last_sync_api_football", "at": sync_start, "ok": True, "created": created, "updated": updated, "skipped": skipped, "finished_applied": finished_applied}},
        upsert=True,
    )

    logger.info("IMPORT FINISHED")
    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "finished_applied": finished_applied,
        "synced_at": sync_start,
    }


@api_router.post("/admin/api-football/sync-results")
async def admin_api_football_sync_results(_staff=Depends(require_staff)):
    """Sync results for already imported API-Football fixtures."""
    sync_start = datetime.now(timezone.utc).isoformat()

    # Only imported matches not finished and already started (kickoff <= now + small tolerance)
    now = datetime.now(timezone.utc)
    limit = 200

    matches = await db.matches.find(
        {
            "external_provider": "api_football",
            "external_fixture_id": {"$exists": True},
            "status": {"$ne": "finished"},
        },
        {"_id": 0, "id": 1, "external_fixture_id": 1, "kickoff": 1}
    ).sort("kickoff", -1).limit(limit).to_list(limit)

    checked = 0
    updated = 0

    for m in matches:
        kickoff_dt = _parse_dt(m.get("kickoff"))
        if kickoff_dt and kickoff_dt > now + timedelta(minutes=1):
            # upcoming, skip
            continue

        fid = m.get("external_fixture_id")
        if not fid:
            continue

        checked += 1
        try:
            payload = await api_football_get("/fixtures", {"id": int(fid)})
            resp = payload.get("response") or []
            if not resp:
                continue
            item = resp[0]
            fixture = item.get("fixture") or {}
            status_short = (fixture.get("status") or {}).get("short")
            if status_short not in API_FOOTBALL_FINISHED_SHORT:
                continue
            goals = item.get("goals") or {}
            h = goals.get("home")
            a = goals.get("away")
            if not isinstance(h, int) or not isinstance(a, int):
                continue

            await apply_match_result(m["id"], int(h), int(a), source="auto")
            await db.matches.update_one(
                {"id": m["id"]},
                {"$set": {"result_provider": "api_football"}}
            )
            updated += 1
        except Exception as e:
            logger.warning(f"API-Football sync fixture {fid} failed: {e}")

    await db.app_state.update_one(
        {"key": "last_sync_api_football"},
        {"$set": {"key": "last_sync_api_football", "at": sync_start, "ok": True, "updated": updated, "checked": checked}},
        upsert=True,
    )

    return {"ok": True, "updated": updated, "checked": checked, "synced_at": sync_start}


@api_router.get("/admin/api-football/last-sync")
async def admin_api_football_last_sync(_staff=Depends(require_staff)):
    doc = await db.app_state.find_one({"key": "last_sync_api_football"}, {"_id": 0})
    return doc or {"at": None, "ok": None, "updated": 0, "checked": 0, "created": 0, "skipped": 0}


@api_router.delete("/admin/delete-season")
async def delete_season(
    season:int,
    _staff=Depends(require_staff)
):
    result = await db.matches.delete_many({
        "external_provider":"api_football",
        "season":season,
        "league_id":{"$ne":1}
    })
    return {
        "ok":True,
        "deleted":result.deleted_count
    }



async def auto_sync_api_football_results_loop():
    """Background: periodically sync results for imported API-Football matches."""
    await asyncio.sleep(45)
    while True:
        try:
            # do not hammer API; every 5 minutes
            await admin_api_football_sync_results()  # uses staff dependency normally; here direct call
        except Exception as e:
            logger.warning(f"Auto API-Football sync loop failed: {e}")
        await asyncio.sleep(300)


# ===============================
# Public API-Football Endpoints
# ===============================
@api_router.get("/football/leagues")
async def football_leagues(search: Optional[str] = None):
    params = {}
    if search:
        params["search"] = search
    data = await cached_api_football_get("/leagues", params)
    items = [simplify_league_row(x) for x in (data.get("response") or [])]
    return {"count": len(items), "items": items}


@api_router.get("/football/fixtures")
async def football_fixtures(
    date: Optional[str] = None,
    league_id: Optional[int] = None,
    season: Optional[int] = None,
    round: Optional[str] = None,
    live: Optional[bool] = None,
    status_short: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    params = {}
    if date:
        params["date"] = date
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if league_id:
        params["league"] = league_id
    if season:
        params["season"] = season
    if round:
        params["round"] = round
    if live:
        params["live"] = "all"
    if status_short:
        params["status"] = status_short

    if live:
        payload = await api_football_get("/fixtures", params)
    else:
        payload = await cached_api_football_get(
            "/fixtures",
            params,
            ttl_seconds=900,
        )

    resp = payload.get("response") or []
    items = [simplify_fixture(x) for x in resp]
    return {"count": len(items), "items": items}


@api_router.get("/football/fixtures/today")
async def football_today():
    today = datetime.now(timezone.utc).date().isoformat()
    return await football_fixtures(date=today)


@api_router.get("/football/fixtures/upcoming")
async def football_upcoming(days: int = 3):
    days = max(1, min(days, 14))
    now = datetime.now(timezone.utc).date()
    from_date = now.isoformat()
    to_date = (now + timedelta(days=days)).isoformat()
    return await football_fixtures(from_date=from_date, to_date=to_date)


@api_router.get("/football/fixtures/live")
async def football_live():
    return await football_fixtures(live=True)


@api_router.get("/football/fixtures/finished")
async def football_finished(date: Optional[str] = None):
    d = date or datetime.now(timezone.utc).date().isoformat()
    # status=FT returns finished, but some competitions use AET/PEN; for broad we fetch date and filter here
    payload = await cached_api_football_get(
        "/fixtures",
        {"date": d},
        ttl_seconds=60,
    )
    resp = payload.get("response") or []
    items = []
    for x in resp:
        short = ((x.get("fixture") or {}).get("status") or {}).get("short")
        if short in API_FOOTBALL_FINISHED_SHORT:
            items.append(simplify_fixture(x))
    return {"count": len(items), "items": items}


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



# ---------- Marquee ----------

class MarqueeItem(BaseModel):
    id: str
    enabled: bool = True
    text: str
    speed: int = 18
    textColor: str = "#FFD700"
    background: str = "#000000"
    fontSize: int = 18
    fontWeight: str = "700"


class MarqueeIn(BaseModel):
    items: list[MarqueeItem] = Field(default_factory=list)


@api_router.get("/marquee")
async def get_marquee():
    doc = await db.app_state.find_one({"key":"marquee"},{"_id":0})

    if doc and doc.get("items"):
        return {
            "items": doc["items"],
            "text": next(
                (i["text"] for i in doc["items"] if i.get("enabled")),
                ""
            )
        }

    text = (
        (doc or {}).get("text")
        or "🏆 الرعاة الرسميون لجائزة ملك التوقعات | ⭐ قيس العدار | ⭐ الياس الخياري | ⭐ حمزة القاضي | 🏆"
    )

    return {
        "text": text,
        "items": [
            {
                "id":"1",
                "enabled":True,
                "text":text,
                "speed":18,
                "textColor":"#FFD700",
                "background":"#000000",
                "fontSize":18,
                "fontWeight":"700"
            }
        ]
    }


@api_router.put("/admin/marquee")
async def update_marquee(data: MarqueeIn, _admin=Depends(require_admin)):

    items=[]

    for item in data.items:
        d = item.model_dump() if hasattr(item,"model_dump") else item.dict()
        d["text"] = str(d.get("text",""))[:500]
        items.append(d)

    await db.app_state.update_one(
        {"key":"marquee"},
        {
            "$set":{
                "key":"marquee",
                "items":items,
                "text":next((i["text"] for i in items if i.get("enabled")), ""),
                "updated_at":datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )

    return {
        "ok":True,
        "count":len(items)
    }

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
                android=messaging.AndroidConfig(
                    priority="high",
                    ttl=3600,
                    notification=messaging.AndroidNotification(
                        channel_id="king_high",
                        priority="high",
                        sound="default",
                        default_sound=True,
                        default_vibrate_timings=True,
                        visibility="public",
                    ),
                ),
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
                android=messaging.AndroidConfig(
                    priority="high",
                    ttl=3600,
                    notification=messaging.AndroidNotification(
                        channel_id="king_high",
                        priority="high",
                        sound="default",
                        default_sound=True,
                        default_vibrate_timings=True,
                        visibility="public",
                    ),
                ),
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
            "kickoff_utc": kickoff_utc.isoformat().replace("+00:00", "Z"),
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
    if len(data.matches) > 31:
        raise HTTPException(status_code=400, detail="عدد مباريات التحدي يتجاوز الحد المسموح به للشجرة")

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
    "round32": 1,
    "round16": 2,
    "quarterFinals": 3,
    "semiFinals": 4,
    "champion": 10,
}


class ChallengePredictionIn(BaseModel):
    round32: dict = Field(default_factory=dict)
    round16: dict = Field(default_factory=dict)
    quarterFinals: dict = Field(default_factory=dict)
    semiFinals: dict = Field(default_factory=dict)
    final: dict = Field(default_factory=dict)
    champion: dict = Field(default_factory=dict)


class ChallengeResultsIn(BaseModel):
    round32: dict = Field(default_factory=dict)
    round16: dict = Field(default_factory=dict)
    quarterFinals: dict = Field(default_factory=dict)
    semiFinals: dict = Field(default_factory=dict)
    final: dict = Field(default_factory=dict)
    champion: dict = Field(default_factory=dict)


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



async def recalculate_challenge_scores():
    results_doc = await db.challenge_results.find_one(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    )

    if not results_doc:
        return

    results = results_doc.get("results", {})

    predictions = await db.challenge_predictions.find(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    ).to_list(10000)

    now = datetime.now(timezone.utc).isoformat()

    for pred in predictions:
        score, details = calculate_challenge_score(
            pred.get("prediction", {}),
            results,
        )

        await db.challenge_predictions.update_one(
            {
                "challenge_id": CHALLENGE_ID,
                "user_id": pred["user_id"],
            },
            {
                "$set": {
                    "score": score,
                    "details": details,
                    "score_updated_at": now,
                }
            },
        )


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

    old_doc = await db.challenge_results.find_one(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    )

    merged = (old_doc or {}).get("results", {})

    for key in [
        "round32",
        "round16",
        "quarterFinals",
        "semiFinals",
        "final",
    ]:
        merged.setdefault(key, {})
        merged[key].update(results.get(key, {}))

    if results.get("champion"):
        merged["champion"] = results["champion"]

    doc = {
        "challenge_id": CHALLENGE_ID,
        "results": merged,
        "updated_at": now,
    }

    await db.challenge_results.update_one(
        {"challenge_id": CHALLENGE_ID},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    await recalculate_challenge_scores()

    return {
        "success": True,
        "message": "تم حفظ نتائج التحدي",
        "results": results,
        "updated_at": now,
    }


@api_router.post("/admin/challenge/results/reset")
async def reset_challenge_results(_staff=Depends(require_staff)):
    await db.challenge_results.delete_one({"challenge_id": CHALLENGE_ID})
    return {"success": True, "message": "تم تصفير نتائج التحدي بنجاح"}



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
CHALLENGE_LOCK_AT = os.environ.get("CHALLENGE_LOCK_AT", "2026-07-18T21:00:00+00:00")


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
    await db.matches.create_index("kickoff")
    await db.matches.create_index("match_date")
    await db.matches.create_index("status")
    await db.matches.create_index([("match_date", 1), ("kickoff_utc", 1)])
    await db.matches.create_index([("home_team", 1), ("away_team", 1)])
    # API-Football uniqueness / performance
    await db.matches.create_index("external_provider")
    await db.matches.create_index("external_fixture_id", unique=True, sparse=True)

    await db.predictions.create_index([("user_id", 1), ("match_id", 1)], unique=True)
    await db.predictions.create_index("user_id")
    await db.predictions.create_index("match_id")
    await db.predictions.create_index([("match_id", 1), ("points", 1)])

    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    await db.notifications.create_index([("user_id", 1), ("read", 1)])

    await db.chat_messages.create_index("created_at")

    await db.push_tokens.create_index("token", unique=True)
    await db.push_tokens.create_index("user_id")

    # football teams
    await db.football_teams.create_index("code", unique=True)
    await db.football_teams.create_index("api_football_team_id")

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
        "kickoff_utc": kickoff,
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
async def external_live_matches(all: bool = False):
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
        "UEFA Europa League",
        "UEFA Europa Conference League",
    }

    items = []
    for item in payload.get("response", []):
        fixture = item.get("fixture", {})
        league = item.get("league", {})

        if not all and league.get("name") not in ALLOWED_LIVE_LEAGUES:
            continue
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        status = fixture.get("status", {})

        home = teams.get("home", {}) or {}
        away = teams.get("away", {}) or {}

        items.append({
            "id": fixture.get("id"),
            "league": league_ar_name(league.get("name")),
            "league_en": league.get("name"),
            "league_id": league.get("id"),
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
    try:
        events = await fetch_world_cup_events()
    except Exception as e:
        print(f"فشل جلب المباريات من المصدر الخارجي: {e}")
        events = []

    created = 0
    skipped = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    MECCA = timezone(timedelta(hours=3))

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

        stage = ev.get("strRound") or ev.get("strStage") or "مرحلة المجموعات"

        doc = {
            "id": str(uuid.uuid4()),
            "home_team": h_code,
            "away_team": a_code,
            "match_date": kickoff.date().isoformat(),
            "kickoff": kickoff.astimezone(timezone.utc).isoformat(),
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

    # استخدام الرموز المعتمدة المكونة من 3 أحرف
    EXACT_R32_FIXTURES = [
        ("RSA", "CAN", "2026-06-28", "22:00"),
        ("BRA", "JPN", "2026-06-29", "20:00"),
        ("GER", "PAR", "2026-06-29", "23:30"),
        ("NED", "MAR", "2026-06-30", "04:00"),
        ("CIV", "NOR", "2026-06-30", "20:00"),
        ("FRA", "SWE", "2026-07-01", "00:00"),
        ("MEX", "TBD", "2026-07-01", "04:00"),
        ("TBD", "TBD", "2026-07-01", "19:00"),
        ("BEL", "TBD", "2026-07-01", "23:00"),
        ("USA", "BIH", "2026-07-02", "03:00"),
        ("ESP", "TBD", "2026-07-02", "22:00"),
        ("TBD", "TBD", "2026-07-03", "02:00"),
        ("SUI", "TBD", "2026-07-03", "06:00"),
        ("AUS", "EGY", "2026-07-03", "21:00"),
        ("ARG", "CPV", "2026-07-04", "01:00"),
        ("TBD", "TBD", "2026-07-04", "04:30")
    ]

    for home, away, date_local, time_local in EXACT_R32_FIXTURES:
        existing = await db.matches.find_one({
            "$or": [
                {"home_team": home, "away_team": away},
                {"home_team": away, "away_team": home}
            ]
        })

        if existing:
            skipped += 1
            continue

        h, mnt = map(int, time_local.split(":"))
        y, m, d = map(int, date_local.split("-"))
        mecca_dt = datetime(y, m, d, h, mnt, tzinfo=MECCA)
        kickoff_utc = mecca_dt.astimezone(timezone.utc)
        match_date_mecca = mecca_dt.strftime("%Y-%m-%d")

        doc = {
            "id": str(uuid.uuid4()),
            "home_team": home,
            "away_team": away,
            "match_date": match_date_mecca,
            "kickoff": kickoff_utc.isoformat().replace("+00:00", "Z"),
            "kickoff_utc": kickoff_utc.isoformat().replace("+00:00", "Z"),
            "stage": "دور الـ32",
            "group_name": None,
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
        "message": f"تم بنجاح استيراد {created} مباراة جديدة وتحديث جدول كأس العالم وتحدي دور الـ32!"
    }


@app.on_event("startup")
async def repair_r32_team_names_to_codes():
    try:
        mapping = {
            "جنوب أفريقيا": "RSA", "كندا": "CAN", "البرازيل": "BRA", "اليابان": "JPN",
            "ألمانيا": "GER", "باراغواي": "PAR", "هولندا": "NED", "المغرب": "MAR",
            "ساحل العاج": "CIV", "النرويج": "NOR", "فرنسا": "FRA", "السويد": "SWE",
            "المكسيك": "MEX", "بلجيكا": "BEL", "الولايات المتحدة": "USA", "البوسنة والهرسك": "BIH",
            "إسبانيا": "ESP", "سويسرا": "SUI", "أستراليا": "AUS", "مصر": "EGY",
            "الأرجنتين": "ARG", "الرأس الأخضر": "CPV", "كولومبيا": "COL", "كرواتيا": "CRO",
            "يُحدّد لاحقاً": "TBD"
        }
        for arabic_name, code in mapping.items():
            await db.matches.update_many({"home_team": arabic_name}, {"$set": {"home_team": code}})
            await db.matches.update_many({"away_team": arabic_name}, {"$set": {"away_team": code}})
        print("✅ Successfully repaired database team names to official codes!")
    except Exception as e:
        print("Database repair error:", e)


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
        {"$set": {"kickoff": data.kickoff, "kickoff_utc": data.kickoff}}
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
        {"$set": {"kickoff": data.kickoff, "kickoff_utc": data.kickoff}}
    )

    return {
        "success": True,
        "message": "تم تعديل وقت المباراة بدون حذف التوقعات",
        "match_id": match["id"],
        "kickoff": data.kickoff
    }








# ============================================================
# AUTO SYNC COMPETITION TAB DATA
# ============================================================

AUTO_COMPETITION_LEAGUES = [
    (1, "كأس العالم"),
    (39, "الدوري الإنجليزي"),
    (140, "الدوري الإسباني"),
    (135, "الدوري الإيطالي"),
    (78, "الدوري الألماني"),
    (61, "الدوري الفرنسي"),
]


async def auto_sync_competition_data_once():
    """
    Refresh competition-tab datasets only.

    This function writes to competition_data only through
    sync_competition_dataset().

    It does NOT touch:
    - db.matches
    - db.predictions
    - prediction points
    - user total_points
    """

    started_at = datetime.now(timezone.utc).isoformat()

    results = []

    logger.info(
        "AUTO COMPETITION SYNC START leagues=%s",
        len(AUTO_COMPETITION_LEAGUES),
    )

    for index, (league_id, league_name) in enumerate(
        AUTO_COMPETITION_LEAGUES
    ):
        try:
            result = await sync_competition_dataset(
                league_id,
                2026,
            )

            results.append({
                "league_id": league_id,
                "name": league_name,
                "ok": True,
                "matches": result.get("matches", 0),
                "standings": result.get("standings", 0),
                "teams": result.get("teams", 0),
                "scorers": result.get("scorers", 0),
                "errors": result.get("errors", {}),
            })

            logger.info(
                "AUTO COMPETITION SYNC OK league=%s name=%s "
                "matches=%s standings=%s teams=%s scorers=%s",
                league_id,
                league_name,
                result.get("matches", 0),
                result.get("standings", 0),
                result.get("teams", 0),
                result.get("scorers", 0),
            )

        except Exception as e:
            results.append({
                "league_id": league_id,
                "name": league_name,
                "ok": False,
                "error": repr(e),
            })

            logger.warning(
                "AUTO COMPETITION SYNC FAILED league=%s name=%s: %r",
                league_id,
                league_name,
                e,
            )

        # Football-Data free tier protection.
        # Keep requests well below the provider rate limit.
        if index < len(AUTO_COMPETITION_LEAGUES) - 1:
            await asyncio.sleep(70)

    finished_at = datetime.now(timezone.utc).isoformat()

    await db.app_state.update_one(
        {
            "key": "last_auto_competition_sync"
        },
        {
            "$set": {
                "key": "last_auto_competition_sync",
                "started_at": started_at,
                "finished_at": finished_at,
                "season": 2026,
                "results": results,
            }
        },
        upsert=True,
    )

    logger.info(
        "AUTO COMPETITION SYNC FINISHED"
    )

    return {
        "ok": True,
        "season": 2026,
        "started_at": started_at,
        "finished_at": finished_at,
        "results": results,
    }


async def auto_sync_competition_data_loop():
    """
    Background competition-tab refresh.

    Wait after application startup so deployment can stabilize,
    then refresh every 6 hours.
    """

    await asyncio.sleep(180)

    while True:
        try:
            await auto_sync_competition_data_once()

        except Exception as e:
            logger.warning(
                "AUTO COMPETITION LOOP FAILED: %r",
                e,
            )

        await asyncio.sleep(21600)


@api_router.get("/admin/competitions/auto-sync-status")
async def admin_competition_auto_sync_status(
    _staff=Depends(require_staff),
):
    doc = await db.app_state.find_one(
        {
            "key": "last_auto_competition_sync"
        },
        {
            "_id": 0
        },
    )

    return doc or {
        "key": "last_auto_competition_sync",
        "started_at": None,
        "finished_at": None,
        "season": 2026,
        "results": [],
    }


@api_router.post("/admin/competitions/auto-sync-now")
async def admin_competition_auto_sync_now(
    _staff=Depends(require_staff),
):
    return await auto_sync_competition_data_once()


@app.on_event("startup")
async def start_auto_sync_results():
    asyncio.create_task(auto_sync_results_loop())
    asyncio.create_task(auto_match_reminders_loop())
    asyncio.create_task(auto_sync_api_football_results_loop())
    asyncio.create_task(auto_sync_competition_data_loop())




# ===== TEMP ADMIN: Recalculate Challenge Scores =====
@api_router.post("/admin/challenge/recalculate")
async def admin_recalculate_challenge_scores(_staff=Depends(require_staff)):
    await recalculate_challenge_scores()

    results_doc = await db.challenge_results.find_one(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    )

    predictions = await db.challenge_predictions.find(
        {"challenge_id": CHALLENGE_ID},
        {"_id": 0},
    ).to_list(10000)

    updated = 0

    for pred in predictions:
        score, details = calculate_challenge_score(
            pred.get("prediction", {}),
            (results_doc or {}).get("results", {}),
        )

        await db.challenge_predictions.update_one(
            {
                "challenge_id": CHALLENGE_ID,
                "user_id": pred["user_id"],
            },
            {
                "$set": {
                    "score": score,
                    "details": details,
                }
            },
        )

        updated += 1

    return {
        "success": True,
        "updated": updated,
    }

# ===== END TEMP =====



# ============================================================
# COMPETITIONS API
# ============================================================

# Football-Data.org is used for current 2026/2027 competition fixtures
# where the current API-Football plan does not expose the requested season.
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"

FOOTBALL_DATA_COMPETITIONS = {
    1: "WC",     # FIFA World Cup
    39: "PL",    # Premier League
    140: "PD",   # La Liga
    135: "SA",   # Serie A
    78: "BL1",   # Bundesliga
    61: "FL1",   # Ligue 1
    2: "CL",     # UEFA Champions League
}


def football_data_status_short(status):
    value = str(status or "").upper().strip()

    mapping = {
        "SCHEDULED": "NS",
        "TIMED": "NS",
        "IN_PLAY": "LIVE",
        "PAUSED": "HT",
        "FINISHED": "FT",
        "SUSPENDED": "SUSP",
        "POSTPONED": "PST",
        "CANCELLED": "CANC",
        "AWARDED": "FT",
    }

    return mapping.get(value, value or "NS")


def simplify_football_data_match(item, league_id, season):
    competition = item.get("competition") or {}
    home = item.get("homeTeam") or {}
    away = item.get("awayTeam") or {}
    score = item.get("score") or {}
    full_time = score.get("fullTime") or {}

    status_name = item.get("status")
    status_short = football_data_status_short(status_name)

    home_score = full_time.get("home")
    away_score = full_time.get("away")

    return {
        "fixture_id": f"fd:{item.get('id')}",
        "external_provider": "football_data",
        "external_fixture_id": item.get("id"),
        "timestamp": int(
            datetime.fromisoformat(
                str(item.get("utcDate")).replace("Z", "+00:00")
            ).timestamp()
        ) if item.get("utcDate") else 0,
        "kickoff_utc": item.get("utcDate"),
        "status": {
            "short": status_short,
            "long": status_name,
            "elapsed": None,
        },
        "league": {
            "id": league_id,
            "name": competition.get("name"),
            "name_en": competition.get("name"),
            "country": None,
            "season": season,
            "round": item.get("matchday"),
            "round_en": (
                f"Regular Season - {item.get('matchday')}"
                if item.get("matchday") is not None
                else item.get("stage")
            ),
        },
        "teams": {
            "home": {
                "id": home.get("id"),
                "code": f"fd:{home.get('id')}",
                "name": home.get("name"),
                "name_en": home.get("name"),
                "name_ar": team_ar_name(home.get("name")),
                "logo": home.get("crest"),
            },
            "away": {
                "id": away.get("id"),
                "code": f"fd:{away.get('id')}",
                "name": away.get("name"),
                "name_en": away.get("name"),
                "name_ar": team_ar_name(away.get("name")),
                "logo": away.get("crest"),
            },
        },
        "goals": {
            "home": home_score,
            "away": away_score,
        },
    }



_HIGHLIGHTLY_LIVE_CACHE = {}
_HIGHLIGHTLY_LIVE_CACHE_TTL = 60


async def enrich_matches_from_highlightly(matches: list):
    """
    Enrich LIVE competition-tab matches from Highlightly only.
    Does not touch db.matches, predictions, points, or scoring.
    """
    key = os.environ.get("HIGHLIGHTLY_API_KEY")

    if not key:
        return matches

    live_matches = [
        match
        for match in matches
        if (match.get("status") or {}).get("short") in {
            "LIVE", "1H", "2H", "HT", "ET", "P", "BT"
        }
    ]

    if not live_matches:
        return matches

    dates = set()

    for match in live_matches:
        kickoff = match.get("kickoff_utc")

        if kickoff:
            dates.add(str(kickoff)[:10])

    headers = {
        "x-rapidapi-key": key,
    }

    highlightly_matches = []

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for match_date in dates:
                now_ts = time.time()
                cached = _HIGHLIGHTLY_LIVE_CACHE.get(match_date)

                if (
                    cached
                    and now_ts - cached["time"] < _HIGHLIGHTLY_LIVE_CACHE_TTL
                ):
                    day_matches = cached["items"]

                    logger.info(
                        "HIGHLIGHTLY LIVE CACHE HIT date=%s",
                        match_date,
                    )
                else:
                    response = await client.get(
                        "https://soccer.highlightly.net/matches",
                        headers=headers,
                        params={
                            "date": match_date,
                            "timezone": "Asia/Riyadh",
                            "limit": 100,
                        },
                    )

                    response.raise_for_status()

                    payload = response.json()
                    day_matches = payload.get("data") or []

                    _HIGHLIGHTLY_LIVE_CACHE[match_date] = {
                        "time": now_ts,
                        "items": day_matches,
                    }

                highlightly_matches.extend(day_matches)

    except Exception as exc:
        logger.warning(
            "HIGHLIGHTLY LIVE ENRICH FAILED error=%s",
            exc,
        )

        return matches

    def normalize_name(value):
        return (
            str(value or "")
            .lower()
            .replace(".", "")
            .replace("-", " ")
            .strip()
        )

    for match in matches:
        status = match.get("status") or {}

        if status.get("short") not in {
            "LIVE", "1H", "2H", "HT", "ET", "P", "BT"
        }:
            continue

        teams = match.get("teams") or {}

        home_name = normalize_name(
            (teams.get("home") or {}).get("name")
        )

        away_name = normalize_name(
            (teams.get("away") or {}).get("name")
        )

        for live_item in highlightly_matches:
            live_home = normalize_name(
                (live_item.get("homeTeam") or {}).get("name")
            )

            live_away = normalize_name(
                (live_item.get("awayTeam") or {}).get("name")
            )

            if (
                home_name == live_home
                and away_name == live_away
            ):
                state = live_item.get("state") or {}
                score = state.get("score") or {}
                current_score = score.get("current")
                clock = state.get("clock")

                if clock is not None:
                    status["elapsed"] = clock

                if current_score:
                    try:
                        home_score, away_score = [
                            int(value.strip())
                            for value in current_score.split("-")
                        ]

                        match["goals"] = {
                            "home": home_score,
                            "away": away_score,
                        }

                    except Exception:
                        pass

                logger.info(
                    "HIGHLIGHTLY LIVE MATCH: %s vs %s minute=%s score=%s",
                    home_name,
                    away_name,
                    clock,
                    current_score,
                )

                break

    return matches


async def fetch_football_data_matches(league_id: int, season: int):
    competition_code = FOOTBALL_DATA_COMPETITIONS.get(int(league_id))

    if not competition_code:
        raise ValueError(
            f"Football-Data competition mapping not found for league {league_id}"
        )

    token = os.environ.get("API_FOOTBALL_KEY") or os.environ.get("FOOTBALL_DATA_TOKEN")

    if not token:
        raise ValueError("API_FOOTBALL_KEY أو FOOTBALL_DATA_TOKEN غير موجود")

    url = (
        f"{FOOTBALL_DATA_BASE_URL}/competitions/"
        f"{competition_code}/matches"
    )

    headers = {
        "X-Auth-Token": token,
    }

    params = {
        "season": int(season),
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            url,
            headers=headers,
            params=params,
        )

        response.raise_for_status()
        payload = response.json()

    matches = [
        simplify_football_data_match(
            item,
            league_id,
            season,
        )
        for item in (payload.get("matches") or [])
    ]

    matches.sort(
        key=lambda x: x.get("timestamp") or 0
    )

    matches = await enrich_matches_from_highlightly(matches)

    return matches


async def football_data_get_competition_dataset(
    league_id: int,
    season: int,
    kind: str,
):
    competition_code = FOOTBALL_DATA_COMPETITIONS.get(int(league_id))

    if not competition_code:
        raise ValueError(
            f"Football-Data competition mapping not found for league {league_id}"
        )

    token = os.environ.get("API_FOOTBALL_KEY") or os.environ.get("FOOTBALL_DATA_TOKEN")

    if not token:
        raise ValueError("API_FOOTBALL_KEY أو FOOTBALL_DATA_TOKEN غير موجود")

    url = (
        f"{FOOTBALL_DATA_BASE_URL}/competitions/"
        f"{competition_code}/{kind}"
    )

    headers = {
        "X-Auth-Token": token,
    }

    params = {
        "season": int(season),
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            url,
            headers=headers,
            params=params,
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")

            raise RuntimeError(
                f"Football-Data rate limit"
                + (
                    f"; retry after {retry_after} seconds"
                    if retry_after
                    else ""
                )
            )

        response.raise_for_status()

        return response.json()


async def fetch_football_data_standings(
    league_id: int,
    season: int,
):
    payload = await football_data_get_competition_dataset(
        league_id,
        season,
        "standings",
    )

    standings = []

    tables = payload.get("standings") or []

    total_tables = [
        table
        for table in tables
        if str(table.get("type") or "").upper() == "TOTAL"
    ]

    if not total_tables and tables:
        total_tables = [tables[0]]

    for table_data in total_tables:
        for row in table_data.get("table") or []:
            team = row.get("team") or {}

            standings.append({
                "rank": row.get("position"),
                "points": row.get("points"),
                "played": row.get("playedGames"),
                "win": row.get("won"),
                "draw": row.get("draw"),
                "lose": row.get("lost"),
                "gf": row.get("goalsFor"),
                "ga": row.get("goalsAgainst"),
                "gd": row.get("goalDifference"),
                "team": {
                    "id": team.get("id"),
                    "code": f"fd:{team.get('id')}",
                    "name_en": team.get("name"),
                    "name_ar": team_ar_name(
                        team.get("name")
                    ),
                    "logo": team.get("crest"),
                },
            })

    standings.sort(
        key=lambda x: (
            x.get("rank") is None,
            x.get("rank") or 9999,
        )
    )

    return standings


async def fetch_football_data_teams(
    league_id: int,
    season: int,
):
    payload = await football_data_get_competition_dataset(
        league_id,
        season,
        "teams",
    )

    teams = []

    for item in payload.get("teams") or []:
        teams.append({
            "id": item.get("id"),
            "code": f"fd:{item.get('id')}",
            "name_en": item.get("name"),
            "name_ar": team_ar_name(
                item.get("name")
            ),
            "logo": item.get("crest"),
            "country": (
                (item.get("area") or {}).get("name")
            ),
        })

    return teams


async def fetch_football_data_scorers(
    league_id: int,
    season: int,
):
    payload = await football_data_get_competition_dataset(
        league_id,
        season,
        "scorers",
    )

    scorers = []

    for item in payload.get("scorers") or []:
        player = item.get("player") or {}
        team = item.get("team") or {}

        scorers.append({
            "player": {
                "id": player.get("id"),
                "name": player.get("name"),
                "firstname": None,
                "lastname": None,
                "photo": None,
            },
            "statistics": [
                {
                    "team": {
                        "id": team.get("id"),
                        "name": team.get("name"),
                        "name_en": team.get("name"),
                        "name_ar": team_ar_name(
                            team.get("name")
                        ),
                        "logo": team.get("crest"),
                    },
                    "league": {
                        "id": league_id,
                        "name": (
                            (
                                payload.get("competition")
                                or {}
                            ).get("name")
                        ),
                        "country": None,
                        "season": season,
                    },
                    "goals": {
                        "total": item.get("goals"),
                        "assists": item.get("assists"),
                        "penalty": item.get("penalties"),
                    },
                    "games": {
                        "appearences": None,
                    },
                }
            ],
        })

    return scorers


async def resolve_competition_season(
    league_id: int,
    requested_season: int | None = None,
) -> int:

    if requested_season is not None:
        return int(requested_season)

    try:
        data = await cached_api_football_get(
            "leagues",
            {"id": league_id},
            ttl_seconds=86400,
        )

        response = data.get("response") or []

        if response:
            seasons = response[0].get("seasons") or []

            years = sorted(
                {
                    int(item["year"])
                    for item in seasons
                    if item.get("year") is not None
                },
                reverse=True,
            )

            # نختار أحدث موسم تسمح به الخطة الحالية
            allowed_years = [
                year
                for year in years
                if year <= CURRENT_API_FOOTBALL_SEASON
            ]

            if allowed_years:
                return allowed_years[0]

    except Exception as e:
        logger.warning(
            "Could not resolve season for league %s: %s",
            league_id,
            e,
        )

    return CURRENT_API_FOOTBALL_SEASON

@api_router.get("/competitions")
async def get_competitions():

    data = await cached_api_football_get(
        "leagues",
        {
            "current": "true"
        }
    )

    ALLOWED_LEAGUES = {
                2,      # UEFA Champions League
        3,      # UEFA Europa League
        848,    # UEFA Europa Conference League
        39,     # Premier League
        140,    # La Liga
        135,    # Serie A
        78,     # Bundesliga
        61,     # Ligue 1
        307,    # Saudi Pro League
    }

    leagues = []

    for item in data.get("response", []):

        row = simplify_league_row(item)

        if row.get("id") not in ALLOWED_LEAGUES:
            continue

        # نفس الموسم الفعلي المستخدم في المباريات والترتيب والفرق والهدافين
        effective_season = await resolve_competition_season(
            int(row["id"])
        )

        # Football-Data labels the 2025/2026 Champions League
        # by its starting year: 2025.
        if int(row["id"]) == 2:
            effective_season = 2025

        row["api_current_season"] = row.get("current_season")
        row["current_season"] = effective_season
        row["effective_season"] = effective_season

        leagues.append(row)

    order = {
        1:0,
        2:1,
        39:2,
        140:3,
        135:4,
        78:5,
        61:6,
        307:7,
        3:8,
        848:9,
    }

    leagues.sort(key=lambda x: order.get(x["id"],999))

    return leagues


async def save_competition_dataset(
    league_id: int,
    season: int,
    kind: str,
    items: list,
):
    now = datetime.now(timezone.utc).isoformat()

    await db.competition_data.update_one(
        {
            "_id": f"{kind}:{league_id}:{season}"
        },
        {
            "$set": {
                "league_id": league_id,
                "season": season,
                "kind": kind,
                "items": items,
                "updated_at": now,
            }
        },
        upsert=True,
    )



COUNTRY_AR_NAMES = {
    "World": "العالم",
    "England": "إنجلترا",
    "Spain": "إسبانيا",
    "Italy": "إيطاليا",
    "Germany": "ألمانيا",
    "France": "فرنسا",
    "Saudi-Arabia": "السعودية",
    "Saudi Arabia": "السعودية",
    "Portugal": "البرتغال",
    "Netherlands": "هولندا",
    "Belgium": "بلجيكا",
    "Scotland": "اسكتلندا",
    "Switzerland": "سويسرا",
    "Austria": "النمسا",
    "Turkey": "تركيا",
    "Greece": "اليونان",
    "Denmark": "الدنمارك",
    "Norway": "النرويج",
    "Sweden": "السويد",
    "Croatia": "كرواتيا",
    "Serbia": "صربيا",
    "Ukraine": "أوكرانيا",
    "Poland": "بولندا",
    "Cyprus": "قبرص",
    "Israel": "إسرائيل",
    "Czech-Republic": "التشيك",
    "Czech Republic": "التشيك",
}

def country_ar_name(name):
    if not name:
        return name
    return COUNTRY_AR_NAMES.get(name, name)


def localize_competition_items(kind: str, items: list) -> list:
    localized = []

    for original in items or []:
        if not isinstance(original, dict):
            localized.append(original)
            continue

        item = dict(original)

        if kind == "matches":
            league = dict(item.get("league") or {})
            league["name_ar"] = league_ar_name(
                league.get("name_en") or league.get("name")
            )
            league["round_ar"] = translate_round_ar(
                league.get("round_en") or league.get("round")
            )
            league["country_ar"] = country_ar_name(
                league.get("country")
            )
            item["league"] = league

            teams = dict(item.get("teams") or {})

            for side in ("home", "away"):
                team = dict(teams.get(side) or {})
                team["name_ar"] = team_ar_name(
                    team.get("name_en") or team.get("name")
                )
                teams[side] = team

            item["teams"] = teams

        elif kind == "teams":
            item["name_ar"] = team_ar_name(
                item.get("name_en") or item.get("name")
            )
            item["country_ar"] = country_ar_name(
                item.get("country")
            )

        elif kind == "standings":
            team = dict(item.get("team") or {})
            team["name_ar"] = team_ar_name(
                team.get("name_en") or team.get("name")
            )
            item["team"] = team

        elif kind == "scorers":
            statistics = []

            for original_stat in item.get("statistics") or []:
                stat = dict(original_stat)

                team = dict(stat.get("team") or {})
                team["name_ar"] = team_ar_name(
                    team.get("name")
                )
                stat["team"] = team

                league = dict(stat.get("league") or {})
                league["name_ar"] = league_ar_name(
                    league.get("name")
                )
                league["country_ar"] = country_ar_name(
                    league.get("country")
                )
                stat["league"] = league

                statistics.append(stat)

            item["statistics"] = statistics

        localized.append(item)

    return localized


async def load_competition_dataset(
    league_id: int,
    season: int,
    kind: str,
):
    doc = await db.competition_data.find_one(
        {
            "_id": f"{kind}:{league_id}:{season}"
        },
        {
            "_id": 0,
            "items": 1,
        },
    )

    if kind == "matches" and league_id in FOOTBALL_DATA_COMPETITIONS:
        try:
            fresh_items = await fetch_football_data_matches(
                league_id,
                season,
            )

            await db.competition_data.update_one(
                {
                    "_id": f"matches:{league_id}:{season}"
                },
                {
                    "$set": {
                        "league_id": league_id,
                        "season": season,
                        "kind": "matches",
                        "items": fresh_items,
                        "source": "football_data",
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )

            return localize_competition_items(
                kind,
                fresh_items,
            )

        except Exception as exc:
            logger.warning(
                "FOOTBALL-DATA LIVE REFRESH FAILED league=%s season=%s error=%s",
                league_id,
                season,
                exc,
            )

    if not doc:
        return []

    items = doc.get("items") or []

    return localize_competition_items(
        kind,
        items,
    )


async def sync_competition_dataset(
    league_id: int,
    season: int,
):
    result = {
        "league_id": league_id,
        "season": season,
        "matches": 0,
        "standings": 0,
        "teams": 0,
        "scorers": 0,
        "skipped": [],
        "errors": {},
    }

    existing = {}

    cursor = db.competition_data.find(
        {
            "league_id": league_id,
            "season": season,
        },
        {
            "_id": 0,
            "kind": 1,
            "items": 1,
        },
    )

    async for doc in cursor:
        kind = doc.get("kind")
        items = doc.get("items") or []

        if kind and items:
            existing[kind] = items

    # =========================
    # MATCHES
    # =========================
    # Always refresh competition-tab matches.
    # This updates competition_data only and does NOT touch:
    # db.matches, db.predictions, user points, or prediction scoring.
    try:

        if (
            league_id in FOOTBALL_DATA_COMPETITIONS
            and (
                season >= 2026
                or (
                    league_id == 2
                    and season == 2025
                )
            )
        ):
            logger.info(
                "COMPETITION MATCHES REFRESH: Football-Data league=%s season=%s",
                league_id,
                season,
            )

            fixtures = await fetch_football_data_matches(
                league_id,
                season,
            )

            match_source = "football_data"

        else:
            logger.info(
                "COMPETITION MATCHES REFRESH: API-Football league=%s season=%s",
                league_id,
                season,
            )

            data = await cached_api_football_get(
                "fixtures",
                {
                    "league": league_id,
                    "season": season,
                },
                ttl_seconds=900,
            )

            fixtures = [
                simplify_fixture(item)
                for item in data.get("response", [])
            ]

            fixtures.sort(
                key=lambda x: x.get("timestamp") or 0
            )

            match_source = "api_football"

        # Protect existing competition-tab data from accidental empty overwrite.
        if fixtures:
            await save_competition_dataset(
                league_id,
                season,
                "matches",
                fixtures,
            )

            result["matches"] = len(fixtures)
            result["matches_source"] = match_source
            result["matches_refreshed"] = True

        else:
            old_matches = existing.get("matches") or []

            result["matches"] = len(old_matches)
            result["matches_source"] = "existing"
            result["matches_refreshed"] = False
            result["errors"]["matches"] = (
                "Provider returned zero fixtures; existing competition data preserved"
            )

    except Exception as e:

        old_matches = existing.get("matches") or []

        result["matches"] = len(old_matches)
        result["matches_source"] = "existing"
        result["matches_refreshed"] = False
        result["errors"]["matches"] = str(e)

        logger.warning(
            "COMPETITION MATCHES REFRESH FAILED league=%s season=%s: %s",
            league_id,
            season,
            e,
        )

    # =========================
    # STANDINGS
    # =========================
    try:

        if (
            league_id in FOOTBALL_DATA_COMPETITIONS
            and (
                season >= 2026
                or (
                    league_id == 2
                    and season == 2025
                )
            )
        ):
            logger.info(
                "COMPETITION STANDINGS REFRESH: Football-Data league=%s season=%s",
                league_id,
                season,
            )

            standings = await fetch_football_data_standings(
                league_id,
                season,
            )

            standings_source = "football_data"

        else:
            logger.info(
                "COMPETITION STANDINGS REFRESH: API-Football league=%s season=%s",
                league_id,
                season,
            )

            data = await cached_api_football_get(
                "standings",
                {
                    "league": league_id,
                    "season": season,
                },
                ttl_seconds=1800,
            )

            standings = []

            for league in data.get("response", []):
                tables = (
                    league.get("league", {})
                    .get("standings", [])
                )

                for table in tables:
                    for team in table:
                        team_data = team.get("team", {})
                        all_data = team.get("all", {})
                        goals = all_data.get("goals", {})

                        standings.append({
                            "rank": team.get("rank"),
                            "points": team.get("points"),
                            "played": all_data.get("played"),
                            "win": all_data.get("win"),
                            "draw": all_data.get("draw"),
                            "lose": all_data.get("lose"),
                            "gf": goals.get("for"),
                            "ga": goals.get("against"),
                            "gd": team.get("goalsDiff"),
                            "team": {
                                "id": team_data.get("id"),
                                "code": af_team_code(
                                    team_data.get("id")
                                ),
                                "name_en": team_data.get("name"),
                                "name_ar": team_ar_name(
                                    team_data.get("name")
                                ),
                                "logo": team_data.get("logo"),
                            },
                        })

            standings_source = "api_football"

        if standings:
            await save_competition_dataset(
                league_id,
                season,
                "standings",
                standings,
            )

            result["standings"] = len(standings)
            result["standings_source"] = standings_source
            result["standings_refreshed"] = True

        else:
            old_standings = existing.get("standings") or []

            result["standings"] = len(old_standings)
            result["standings_source"] = "existing"
            result["standings_refreshed"] = False

    except Exception as e:

        old_standings = existing.get("standings") or []

        result["standings"] = len(old_standings)
        result["standings_source"] = "existing"
        result["standings_refreshed"] = False
        result["errors"]["standings"] = repr(e)

        logger.warning(
            "COMPETITION STANDINGS REFRESH FAILED league=%s season=%s: %r",
            league_id,
            season,
            e,
        )

    # =========================
    # TEAMS
    # =========================
    try:

        if (
            league_id in FOOTBALL_DATA_COMPETITIONS
            and (
                season >= 2026
                or (
                    league_id == 2
                    and season == 2025
                )
            )
        ):
            logger.info(
                "COMPETITION TEAMS REFRESH: Football-Data league=%s season=%s",
                league_id,
                season,
            )

            teams = await fetch_football_data_teams(
                league_id,
                season,
            )

            teams_source = "football_data"

        else:
            logger.info(
                "COMPETITION TEAMS REFRESH: API-Football league=%s season=%s",
                league_id,
                season,
            )

            data = await cached_api_football_get(
                "teams",
                {
                    "league": league_id,
                    "season": season,
                },
                ttl_seconds=86400,
            )

            teams = []

            for item in data.get("response", []):
                team = item.get("team", {})

                teams.append({
                    "id": team.get("id"),
                    "name_en": team.get("name"),
                    "name_ar": team_ar_name(
                        team.get("name")
                    ),
                    "logo": team.get("logo"),
                    "country": team.get("country"),
                })

            teams_source = "api_football"

        if teams:
            await save_competition_dataset(
                league_id,
                season,
                "teams",
                teams,
            )

            result["teams"] = len(teams)
            result["teams_source"] = teams_source
            result["teams_refreshed"] = True

        else:
            old_teams = existing.get("teams") or []

            result["teams"] = len(old_teams)
            result["teams_source"] = "existing"
            result["teams_refreshed"] = False

    except Exception as e:

        old_teams = existing.get("teams") or []

        result["teams"] = len(old_teams)
        result["teams_source"] = "existing"
        result["teams_refreshed"] = False
        result["errors"]["teams"] = repr(e)

        logger.warning(
            "COMPETITION TEAMS REFRESH FAILED league=%s season=%s: %r",
            league_id,
            season,
            e,
        )

    # =========================
    # SCORERS
    # =========================
    try:

        if (
            league_id in FOOTBALL_DATA_COMPETITIONS
            and (
                season >= 2026
                or (
                    league_id == 2
                    and season == 2025
                )
            )
        ):
            logger.info(
                "COMPETITION SCORERS REFRESH: Football-Data league=%s season=%s",
                league_id,
                season,
            )

            scorers = await fetch_football_data_scorers(
                league_id,
                season,
            )

            scorers_source = "football_data"

        else:
            logger.info(
                "COMPETITION SCORERS REFRESH: API-Football league=%s season=%s",
                league_id,
                season,
            )

            data = await cached_api_football_get(
                "players/topscorers",
                {
                    "league": league_id,
                    "season": season,
                },
                ttl_seconds=3600,
            )

            scorers = data.get("response", []) or []
            scorers_source = "api_football"

        if scorers:
            await save_competition_dataset(
                league_id,
                season,
                "scorers",
                scorers,
            )

            result["scorers"] = len(scorers)
            result["scorers_source"] = scorers_source
            result["scorers_refreshed"] = True

        else:
            old_scorers = existing.get("scorers") or []

            result["scorers"] = len(old_scorers)
            result["scorers_source"] = "existing"
            result["scorers_refreshed"] = False

    except Exception as e:

        old_scorers = existing.get("scorers") or []

        result["scorers"] = len(old_scorers)
        result["scorers_source"] = "existing"
        result["scorers_refreshed"] = False
        result["errors"]["scorers"] = repr(e)

        logger.warning(
            "COMPETITION SCORERS REFRESH FAILED league=%s season=%s: %r",
            league_id,
            season,
            e,
        )

    return result


@api_router.post("/admin/competitions/{league_id}/sync")
async def sync_competition(
    league_id: int,
    season: Optional[int] = None,
    _staff=Depends(require_staff),
):
    season = await resolve_competition_season(
        league_id,
        season,
    )

    return await sync_competition_dataset(
        league_id,
        season,
    )


@api_router.get("/competitions/{league_id}/matches")
async def get_competition_matches(
    league_id: int,
    season: Optional[int] = None,
):
    # إخفاء مباريات كأس العالم من تبويب البطولات
    if league_id == 1:
        return []
    season = await resolve_competition_season(
        league_id,
        season,
    )

    return await load_competition_dataset(
        league_id,
        season,
        "matches",
    )


@api_router.get("/competitions/{league_id}/standings")
async def get_competition_standings(
    league_id: int,
    season: Optional[int] = None,
):
    season = await resolve_competition_season(
        league_id,
        season,
    )

    return await load_competition_dataset(
        league_id,
        season,
        "standings",
    )


@api_router.get("/competitions/{league_id}/teams")
async def get_competition_teams(
    league_id: int,
    season: Optional[int] = None,
):
    season = await resolve_competition_season(
        league_id,
        season,
    )

    return await load_competition_dataset(
        league_id,
        season,
        "teams",
    )


@api_router.get("/competitions/{league_id}/scorers")
async def get_competition_scorers(
    league_id: int,
    season: Optional[int] = None,
):
    season = await resolve_competition_season(
        league_id,
        season,
    )

    return await load_competition_dataset(
        league_id,
        season,
        "scorers",
    )


# ===== Final World Cup Challenge API =====

FINAL_CHALLENGE_ID = "worldcup2026_final_awards"

# 19 يوليو 2026 الساعة 22:00 بتوقيت مكة = 19:00 UTC
FINAL_CHALLENGE_CLOSE_AT = datetime(
    2026, 7, 18, 21, 0, 0, tzinfo=timezone.utc
)

FINAL_CHALLENGE_POINTS = {
    "champion": 10,
    "best_player": 5,
    "top_scorer": 5,
}


class FinalChallengeEntryIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=7, max_length=20)
    champion: str = Field(min_length=2, max_length=100)
    best_player: str = Field(min_length=2, max_length=120)
    top_scorer: str = Field(min_length=2, max_length=120)


class FinalChallengeResultsIn(BaseModel):
    champion: str = Field(min_length=2, max_length=100)
    best_player: str = Field(min_length=2, max_length=120)
    top_scorer: str = Field(min_length=2, max_length=120)


class FinalChallengeTamkeenVerifyIn(BaseModel):
    verified: bool




def calculate_final_challenge_score(entry, results):
    score = 0

    details = {
        "champion": 0,
        "best_player": 0,
        "top_scorer": 0,
    }

    for key, points in FINAL_CHALLENGE_POINTS.items():
        if key in ("best_player", "top_scorer"):
            matched = final_challenge_player_name_matches(
                entry.get(key),
                results.get(key),
            )
        else:
            predicted = normalize_final_challenge_answer(entry.get(key))
            correct = normalize_final_challenge_answer(results.get(key))
            matched = bool(predicted and correct and predicted == correct)

        if matched:
            score += points
            details[key] = points

    return score, details


async def recalculate_final_challenge_scores():
    results_doc = await db.final_challenge_results.find_one(
        {"challenge_id": FINAL_CHALLENGE_ID},
        {"_id": 0},
    )

    if not results_doc:
        return 0

    results = results_doc.get("results", {})

    entries = await db.final_challenge_entries.find(
        {"challenge_id": FINAL_CHALLENGE_ID},
        {"_id": 0},
    ).to_list(100000)

    now = datetime.now(timezone.utc).isoformat()
    updated = 0

    for entry in entries:
        if entry.get("tamkeen_verified", False):
            score, details = calculate_final_challenge_score(entry, results)
        else:
            score = 0
            details = {
                "champion": 0,
                "best_player": 0,
                "top_scorer": 0,
            }

        await db.final_challenge_entries.update_one(
            {"id": entry["id"]},
            {
                "$set": {
                    "score": score,
                    "score_details": details,
                    "score_updated_at": now,
                }
            },
        )

        updated += 1

    return updated


@api_router.get("/final-challenge/status")
async def get_final_challenge_status():
    return {
        "challenge_id": FINAL_CHALLENGE_ID,
        "closed": final_challenge_is_closed(),
        "close_at": FINAL_CHALLENGE_CLOSE_AT.isoformat(),
        "close_at_makkah": "2026-07-19T22:00:00+03:00",
        "points": FINAL_CHALLENGE_POINTS,
        "max_points": 20,
    }


@api_router.post("/final-challenge/entry")
async def save_final_challenge_entry(data: FinalChallengeEntryIn):
    if final_challenge_is_closed():
        raise HTTPException(
            status_code=403,
            detail="تم إغلاق توقعات تحدي كأس العالم",
        )

    phone = normalize_final_challenge_phone(data.phone)

    if len(phone) < 7:
        raise HTTPException(
            status_code=400,
            detail="رقم الجوال غير صالح",
        )

    now = datetime.now(timezone.utc).isoformat()

    existing = await db.final_challenge_entries.find_one(
        {
            "challenge_id": FINAL_CHALLENGE_ID,
            "phone_normalized": phone,
        },
        {"_id": 0},
    )

    doc = {
        "challenge_id": FINAL_CHALLENGE_ID,
        "name": data.name.strip(),
        "phone": data.phone.strip(),
        "phone_normalized": phone,
        "champion": data.champion.strip(),
        "best_player": data.best_player.strip(),
        "top_scorer": data.top_scorer.strip(),
        "updated_at": now,
    }

    if existing:
        await db.final_challenge_entries.update_one(
            {"id": existing["id"]},
            {"$set": doc},
        )

        entry_id = existing["id"]
        message = "تم تحديث توقعاتك بنجاح"
    else:
        entry_id = str(uuid.uuid4())

        doc.update({
            "id": entry_id,
            "score": 0,
            "score_details": {
                "champion": 0,
                "best_player": 0,
                "top_scorer": 0,
            },
            "tamkeen_verified": False,
            "tamkeen_verified_at": None,
            "tamkeen_verified_by": None,
        },
    ).sort([
        ("score", -1),
        ("created_at", 1),
    ]).to_list(10000)

    leaderboard = []
    previous_score = None
    current_rank = 0

    for index, entry in enumerate(entries, start=1):
        score = int(entry.get("score", 0) or 0)

        if previous_score is None or score != previous_score:
            current_rank = index

        leaderboard.append({
            "rank": current_rank,
            "id": entry.get("id"),
            "name": entry.get("name"),
            "score": score,
            "score_details": entry.get("score_details", {}),
            "tamkeen_verified": bool(entry.get("tamkeen_verified", False)),
            "prize_eligible": bool(entry.get("tamkeen_verified", False)),
        })

        previous_score = score

    return leaderboard

@api_router.post("/admin/final-challenge/results")
async def set_final_challenge_results(
    data: FinalChallengeResultsIn,
    current_user=Depends(require_admin),
):
    now = datetime.now(timezone.utc).isoformat()

    results = {
        "champion": data.champion.strip(),
        "best_player": data.best_player.strip(),
        "top_scorer": data.top_scorer.strip(),
    }

    await db.final_challenge_results.update_one(
        {"challenge_id": FINAL_CHALLENGE_ID},
        {
            "$set": {
                "challenge_id": FINAL_CHALLENGE_ID,
                "results": results,
                "updated_at": now,
                "updated_by": current_user["id"],
            }
        },
        upsert=True,
    )

    updated = await recalculate_final_challenge_scores()

    return {
        "success": True,
        "message": "تم حفظ النتائج واحتساب نقاط التحدي",
        "updated_entries": updated,
        "results": results,
    }


@api_router.delete("/admin/final-challenge/results/reset")
async def reset_final_challenge_results(
    current_user=Depends(require_admin),
):
    now = datetime.now(timezone.utc).isoformat()

    await db.final_challenge_results.delete_many(
        {"challenge_id": FINAL_CHALLENGE_ID}
    )

    result = await db.final_challenge_entries.update_many(
        {"challenge_id": FINAL_CHALLENGE_ID},
        {
            "$set": {
                "score": 0,
                "score_details": {
                    "champion": 0,
                    "best_player": 0,
                    "top_scorer": 0,
                },
                "score_updated_at": now,
            }
        },
    )

    return {
        "success": True,
        "message": "تم تصفير نتائج ونقاط التحدي بنجاح",
        "reset_entries": result.modified_count,
    }


@api_router.get("/admin/final-challenge/results")
async def get_final_challenge_results(
    current_user=Depends(require_staff)
):
    doc = await db.final_challenge_results.find_one(
        {"challenge_id": FINAL_CHALLENGE_ID},
        {"_id": 0},
    )

    return doc or {
        "challenge_id": FINAL_CHALLENGE_ID,
        "results": {},
    }


# ===== End Final World Cup Challenge API =====

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


@app.on_event("startup")
async def fix_corrupted_fields():
    try:
        # تحويل اسم الحقل من kickoff_utc إلى kickoff لجميع المباريات التالفة
        result = await db.matches.update_many(
            {"kickoff": {"$exists": False}, "kickoff_utc": {"$exists": True}},
            [{"$set": {"kickoff": "$kickoff_utc"}}]
        )
        print(f"✅ تم إصلاح وتصحيح مواعيد {result.modified_count} مباراة في قاعدة البيانات!")
    except Exception as e:
        print("خطأ أثناء إصلاح قاعدة البيانات:", e)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
