import asyncio

from server import db, save_competition_dataset


async def main():

    docs = await db.competition_data.find(
        {"kind": "matches"},
        {"_id": 0}
    ).to_list(100)

    print("===== DERIVE TEAMS FROM MATCHES =====")

    for doc in docs:

        league_id = doc["league_id"]
        season = doc["season"]
        matches = doc.get("items") or []

        teams = {}

        for match in matches:

            match_teams = match.get("teams") or {}

            for side in ("home", "away"):

                team = match_teams.get(side) or {}
                team_id = team.get("id")

                if not team_id:
                    continue

                teams[str(team_id)] = {
                    "id": team_id,
                    "name_en": team.get("name_en"),
                    "name_ar": team.get("name_ar"),
                    "logo": team.get("logo"),
                    "country": None,
                }

        items = list(teams.values())

        items.sort(
            key=lambda x: (
                x.get("name_ar")
                or x.get("name_en")
                or ""
            )
        )

        await save_competition_dataset(
            league_id,
            season,
            "teams",
            items,
        )

        print(
            f"League {league_id} / {season}: "
            f"{len(items)} teams"
        )

    count = await db.competition_data.count_documents({})

    print(
        f"\n✅ competition_data documents: {count}"
    )


if __name__ == "__main__":
    asyncio.run(main())
