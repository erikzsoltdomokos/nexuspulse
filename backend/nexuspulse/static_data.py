"""Static game data: Data Dragon items (with offline fallback) and curated champion scaling tiers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache

import httpx

from .config import settings

log = logging.getLogger(__name__)

DDRAGON = "https://ddragon.leagueoflegends.com"


@dataclass(frozen=True)
class ItemInfo:
    item_id: int
    name: str
    cost: int
    attack_damage: float
    health: float
    ability_power: float
    completed: bool


# Approximate offline fallback (used by the synthetic generator and when Data Dragon is unreachable).
_FALLBACK = [
    (3031, "Infinity Edge", 3450, 70, 0, 0), (3153, "Blade of the Ruined King", 3200, 40, 0, 0),
    (3072, "Bloodthirster", 3400, 80, 0, 0), (3036, "Lord Dominik's Regards", 3000, 35, 0, 0),
    (6672, "Kraken Slayer", 3100, 45, 0, 0), (6673, "Immortal Shieldbow", 3000, 55, 0, 0),
    (3094, "Rapid Firecannon", 2650, 0, 0, 0), (3071, "Black Cleaver", 3000, 40, 400, 0),
    (3078, "Trinity Force", 3333, 36, 333, 0), (3053, "Sterak's Gage", 3200, 0, 400, 0),
    (3074, "Ravenous Hydra", 3300, 65, 0, 0), (3142, "Youmuu's Ghostblade", 2800, 60, 0, 0),
    (3089, "Rabadon's Deathcap", 3600, 0, 0, 130), (3157, "Zhonya's Hourglass", 3250, 0, 0, 105),
    (3135, "Void Staff", 3000, 0, 0, 95), (3165, "Morellonomicon", 2950, 0, 350, 75),
    (4645, "Shadowflame", 3200, 0, 0, 110), (6655, "Luden's Companion", 2850, 0, 0, 95),
    (3068, "Sunfire Aegis", 2700, 0, 350, 0), (3075, "Thornmail", 2450, 0, 150, 0),
    (3065, "Spirit Visage", 2700, 0, 400, 0), (3143, "Randuin's Omen", 2700, 0, 350, 0),
    (3190, "Locket of the Iron Solari", 2200, 0, 200, 0), (3107, "Redemption", 2300, 0, 200, 0),
    (3504, "Ardent Censer", 2200, 0, 0, 45), (3050, "Zeke's Convergence", 2200, 0, 300, 0),
    (3006, "Berserker's Greaves", 1100, 0, 0, 0), (3020, "Sorcerer's Shoes", 1100, 0, 0, 0),
    (3047, "Plated Steelcaps", 1100, 0, 0, 0), (3111, "Mercury's Treads", 1100, 0, 0, 0),
]
FALLBACK_ITEMS = {
    i: ItemInfo(i, n, c, ad, hp, ap, True) for (i, n, c, ad, hp, ap) in _FALLBACK
}
AD_ITEMS = [3031, 3153, 3072, 3036, 6672, 6673, 3094, 3142]
AP_ITEMS = [3089, 3157, 3135, 3165, 4645, 6655]
BRUISER_ITEMS = [3071, 3078, 3053, 3074, 3065]
TANK_ITEMS = [3068, 3075, 3065, 3143]
SUPPORT_ITEMS = [3190, 3107, 3504, 3050]
BOOTS = [3006, 3020, 3047, 3111]


def ddragon_version(game_version: str) -> str | None:
    """Map a match gameVersion like '14.19.622.1234' to a Data Dragon version like '14.19.1'."""
    parts = game_version.split(".")
    if len(parts) < 2:
        return None
    prefix = f"{parts[0]}.{parts[1]}."
    try:
        versions = _ddragon_versions()
    except Exception:  # noqa: BLE001 -- offline is a normal condition
        return None
    for v in versions:
        if v.startswith(prefix):
            return v
    return versions[0] if versions else None


@lru_cache(maxsize=1)
def _ddragon_versions() -> list[str]:
    resp = httpx.get(f"{DDRAGON}/api/versions.json", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _parse_ddragon_items(raw: dict) -> dict[int, ItemInfo]:
    items: dict[int, ItemInfo] = {}
    for key, data in raw.get("data", {}).items():
        gold = data.get("gold", {})
        stats = data.get("stats", {})
        total = int(gold.get("total", 0))
        final = not data.get("into")
        is_boots = "Boots" in data.get("tags", [])
        completed = gold.get("purchasable", False) and final and (total >= 2000 or (is_boots and total >= 900))
        items[int(key)] = ItemInfo(
            int(key),
            data.get("name", key),
            total,
            float(stats.get("FlatPhysicalDamageMod", 0)),
            float(stats.get("FlatHPPoolMod", 0)),
            float(stats.get("FlatMagicDamageMod", 0)),
            bool(completed),
        )
    return items


@lru_cache(maxsize=8)
def load_items(game_version: str = "") -> dict[int, ItemInfo]:
    """Item table for a patch: disk cache -> Data Dragon -> offline fallback."""
    version = ddragon_version(game_version) if game_version else None
    cache_dir = settings.data_dir / "ddragon"
    if version:
        path = cache_dir / f"item_{version}.json"
        try:
            if not path.is_file():
                resp = httpx.get(f"{DDRAGON}/cdn/{version}/data/en_US/item.json", timeout=15)
                resp.raise_for_status()
                cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_text(resp.text, encoding="utf-8")
            items = _parse_ddragon_items(json.loads(path.read_text(encoding="utf-8")))
            # Keep fallback entries for ids missing from this patch.
            return {**FALLBACK_ITEMS, **items}
        except Exception as exc:  # noqa: BLE001
            log.warning("Data Dragon items unavailable (%s); using fallback table", exc)
    return dict(FALLBACK_ITEMS)


# Curated scaling tiers: 0 = early game, 1 = mid game (default), 2 = late game.
# This is a hand-maintained heuristic, not Riot data.
_EARLY = """Draven Renekton LeeSin Elise Pantheon Lucian Darius Olaf XinZhao Jayce Leblanc Nidalee
Kalista Blitzcrank Leona Talon Rengar Graves Renata Pyke Rakan Nautilus Thresh Caitlyn Kled Qiyana
Shaco JarvanIV Taliyah Zed Riven Camille Irelia Gragas Sylas Akali Tristana Samira Nilah""".split()
_LATE = """Kayle Kassadin Vayne Jinx KogMaw Veigar Nasus Azir Smolder Aphelios Ryze Cassiopeia Senna
Sona AurelionSol Twitch Viktor Karthus MasterYi Gangplank Sion Kindred Belveth Zeri Seraphine
Yuumi Soraka Anivia Vladimir Ornn Chogath Mordekaiser Kaisa Ezreal Hwei Orianna Syndra Gwen""".split()
CHAMPION_TIER = {**{c: 0 for c in _EARLY}, **{c: 2 for c in _LATE}}
TIER_NAMES = {0: "early", 1: "mid", 2: "late"}


def champion_tier(champion: str) -> int:
    return CHAMPION_TIER.get(champion, 1)
