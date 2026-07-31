import asyncio
import hashlib
import json

from server import (
    db,
    simplify_fixture,
    af_team_code,
    team_ar_name,
    save_competition_dataset,
)

COMPETITIONS = {
    1: 2022,
    2: 2024,
    39: 2024,
    140: 2024,
    135: 2024,
    78: 2024,
    61: 2024,
    307: 2024,
    3: 2024,
    848: 2024,
}


def cache_key(path, params):
    return hashlib.sha1(
        (
            path + "|" +
            json.dumps(params, sort_keys=True)
        ).encode()
    ).hexdigest()


async def get_cached(path, params):
    key = cache_key(path, params)

    doc = await db.competition_cache.find_one(
        {"_id": key},
        {"_id": 0, "data": 1},
    )

    if not doc:
        return None

    return doc.get("data")


async def migrate_matches(league_id, season):
    data = await get_cached(
        "fixtures",
        {
            "league": league_id,
            "season": season,
        },
    )

    if data is None:
        return None

    items = [
        simplify_fixture(item)
        for item in data.get("response", [])
    ]

    items.sort(
        key=lambda x: x.get("timestamp") or 0
    )

    await save_competition_dataset(
        league_id,
        season,
        "matches",
        items,
    )

    return len(items)


async def migrate_standings(league_id, season):
    data = await get_cached(
        "standings",
        {
            "league": league_id,
            "season": season,
        },
    )

    if data is None:
        return None

    items = []

    for league in data.get("response", []):
        for table in (
            league.get("league", {})
            .get("standings", [])
        ):
            for team in table:

                team_data = team.get("team", {})
                all_data = team.get("all", {})
                goals = all_data.get("goals", {})

                items.append({
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

    await save_competition_dataset(
        league_id,
        season,
        "standings",
        items,
    )

    return len(items)


async def migrate_teams(league_id, season):
    data = await get_cached(
        "teams",
        {
            "league": league_id,
            "season": season,
        },
    )

    if data is None:
        return None

    items = []

    for row in data.get("response", []):
        team = row.get("team", {})

        items.append({
            "id": team.get("id"),
            "name_en": team.get("name"),
            "name_ar": team_ar_name(
                team.get("name")
            ),
            "logo": team.get("logo"),
            "country": team.get("country"),
        })

    await save_competition_dataset(
        league_id,
        season,
        "teams",
        items,
    )

    return len(items)


async def migrate_scorers(league_id, season):
    data = await get_cached(
        "players/topscorers",
        {
            "league": league_id,
            "season": season,
        },
    )

    if data is None:
        return None

    items = data.get("response", []) or []

    await save_competition_dataset(
        league_id,
        season,
        "scorers",
        items,
    )

    return len(items)


async def main():

    print("===== CACHE -> MONGODB MIGRATION =====")

    for league_id, season in COMPETITIONS.items():

        print(
            f"\nLeague {league_id} / Season {season}"
        )

        matches = await migrate_matches(
            league_id,
            season,
        )

        standings = await migrate_standings(
            league_id,
            season,
        )

        teams = await migrate_teams(
            league_id,
            season,
        )

        scorers = await migrate_scorers(
            league_id,
            season,
        )

        print(" matches  :", matches)
        print(" standings:", standings)
        print(" teams    :", teams)
        print(" scorers  :", scorers)

    count = await db.competition_data.count_documents({})

    print(
        f"\n✅ competition_data documents: {count}"
    )


if __name__ == "__main__":
    asyncio.run(main())
