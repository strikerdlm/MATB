"""Bounded public traffic acquisition. Provider observations never enter the engine."""

from __future__ import annotations
import asyncio, hashlib, json, math, os, time
from collections import OrderedDict
from pathlib import Path
import httpx
from matb_integration.suas.presentation.geography import data_root, projected_track

MAX_TRACKS = 2000


def number(value):
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalized(provider, payload, received):
    if not isinstance(payload, dict):
        raise ValueError("invalid provider payload")
    rows = payload.get("ac") if provider == "adsb.lol" else payload.get("states")
    if (
        provider == "opensky"
        and rows is None
        and number(payload.get("time")) is not None
    ):
        rows = []
    if not isinstance(rows, list):
        raise ValueError("invalid provider rows")
    now = number(payload.get("now" if provider == "adsb.lol" else "time"))
    if now is None:
        raise ValueError("missing provider timestamp")
    if now > 10_000_000_000:
        now /= 1000
    tracks = {}
    for row in rows[:10000]:
        if provider == "adsb.lol":
            if not isinstance(row, dict):
                continue
            lat, lon = number(row.get("lat")), number(row.get("lon"))
            age = number(row.get("seen_pos"))
            if age is None or age < 0:
                continue
            observed = now - age
            ident = str(row.get("hex", "")).strip().lower()
            geometric = number(row.get("alt_geom"))
            baro = number(row.get("alt_baro"))
            speed = number(row.get("gs"))
            vertical = number(row.get("geom_rate", row.get("baro_rate")))
            track = dict(
                id=ident,
                callsign=str(row.get("flight") or row.get("r") or "").strip()[:32],
                lat=lat,
                lon=lon,
                observed_at=observed,
                geometric_altitude_m=None if geometric is None else geometric * 0.3048,
                barometric_altitude_m=None if baro is None else baro * 0.3048,
                speed_mps=None if speed is None else speed * 0.514444,
                vertical_rate_mps=None if vertical is None else vertical * 0.00508,
                track_deg=number(row.get("track")),
                on_ground=row.get("alt_baro") == "ground",
            )
        else:
            if not isinstance(row, list) or len(row) < 14:
                continue
            ident = str(row[0] or "").strip().lower()
            lat, lon = number(row[6]), number(row[5])
            observed = number(row[3])
            track = dict(
                id=ident,
                callsign=str(row[1] or "").strip()[:32],
                lat=lat,
                lon=lon,
                observed_at=observed,
                geometric_altitude_m=number(row[13]),
                barometric_altitude_m=number(row[7]),
                speed_mps=number(row[9]),
                vertical_rate_mps=number(row[11]),
                track_deg=number(row[10]),
                on_ground=bool(row[8]),
            )
        if (
            not ident
            or len(ident) > 32
            or not all(c in "0123456789abcdef~" for c in ident)
        ):
            continue
        if (
            lat is None
            or lon is None
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
            or observed is None
            or observed > received + 30
        ):
            continue
        if track["speed_mps"] is not None and not 0 <= track["speed_mps"] <= 1500:
            track["speed_mps"] = None
        if track["track_deg"] is not None:
            track["track_deg"] %= 360
        tracks[ident] = {**track, "source": provider, "received_at": received}
        if len(tracks) >= MAX_TRACKS:
            break
    return list(tracks.values())


class TrafficService:
    def __init__(self, fetch=None, clock=time.time):
        self.fetch = fetch
        self.clock = clock
        self.cache = OrderedDict()
        self.lock = asyncio.Lock()
        self.token = None
        self.token_until = 0

    async def _request(self, provider, lat, lon, radius):
        async with httpx.AsyncClient(
            timeout=12,
            follow_redirects=False,
            headers={
                "User-Agent": "MATB-geography/1.0 (+https://github.com/strikerdlm/MATB)"
            },
        ) as client:
            if provider == "adsb.lol":
                return await client.get(
                    f"https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}"
                )
            cid = os.environ.get("OPENSKY_CLIENT_ID")
            secret = os.environ.get("OPENSKY_CLIENT_SECRET")
            if not cid or not secret:
                raise ValueError("OpenSky credentials not configured")
            if self.clock() >= self.token_until:
                r = await client.post(
                    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": cid,
                        "client_secret": secret,
                    },
                )
                r.raise_for_status()
                body = r.json()
                self.token = body["access_token"]
                self.token_until = self.clock() + float(body["expires_in"]) - 60
            dlat = radius / 60
            dlon = dlat / max(0.2, math.cos(math.radians(lat)))
            return await client.get(
                "https://opensky-network.org/api/states/all",
                params={
                    "lamin": lat - dlat,
                    "lamax": lat + dlat,
                    "lomin": lon - dlon,
                    "lomax": lon + dlon,
                },
                headers={"Authorization": f"Bearer {self.token}"},
            )

    async def snapshot(self, lat, lon, radius=50, provider="adsb.lol"):
        if (
            provider not in {"adsb.lol", "opensky"}
            or not all(math.isfinite(v) for v in (lat, lon, radius))
            or not (-5 <= lat <= 16 and -84 <= lon <= -66 and 1 <= radius <= 250)
        ):
            raise ValueError("invalid traffic region")
        key = (provider, round(lat, 2), round(lon, 2), int(radius))
        async with self.lock:
            now = self.clock()
            entry = self.cache.get(key)
            if entry is None or now >= entry["retry_at"]:
                entry = entry or {"tracks": [], "received_at": None}
                try:
                    response = await (
                        self.fetch(*key) if self.fetch else self._request(*key)
                    )
                    now = self.clock()
                    if response.status_code == 429:
                        delay = (
                            number(
                                response.headers.get("X-Rate-Limit-Retry-After-Seconds")
                                or response.headers.get("Retry-After")
                            )
                            or 60
                        )
                        entry.update(
                            status="throttled",
                            retry_at=now + min(86400, max(15, delay)),
                        )
                    else:
                        response.raise_for_status()
                        tracks = normalized(provider, response.json(), now)
                        entry.update(
                            tracks=tracks,
                            received_at=now,
                            status="live" if tracks else "empty",
                            retry_at=now + 15,
                        )
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    entry.update(status="unavailable", retry_at=now + 30)
                self.cache[key] = entry
                self.cache.move_to_end(key)
                while len(self.cache) > 128:
                    self.cache.popitem(last=False)
            tracks = []
            for raw in entry["tracks"]:
                age = max(0, now - raw["observed_at"])
                if age > 60:
                    continue
                # A point endpoint may include boundary rows: enforce the advertised circle.
                distance = (
                    6371008.8
                    * 2
                    * math.asin(
                        min(
                            1,
                            math.sqrt(
                                math.sin(math.radians(raw["lat"] - lat) / 2) ** 2
                                + math.cos(math.radians(lat))
                                * math.cos(math.radians(raw["lat"]))
                                * math.sin(math.radians(raw["lon"] - lon) / 2) ** 2
                            ),
                        )
                    )
                )
                if distance > radius * 1852:
                    continue
                tracks.append({**raw, "age_s": age, "stale": age > 15})
            return {
                "version": 1,
                "provider": provider,
                "status": entry["status"],
                "sampled_at": now,
                "received_at": entry["received_at"],
                "query": {"lat": key[1], "lon": key[2], "radius_nm": key[3]},
                "tracks": tracks,
                "attribution": (
                    "adsb.lol contributors · CC0"
                    if provider == "adsb.lol"
                    else "OpenSky Network · provider terms apply"
                ),
            }


traffic_service = TrafficService()


def recording_path(identifier):
    if (
        not identifier
        or len(identifier) > 64
        or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in identifier)
    ):
        raise ValueError("invalid recording id")
    return data_root() / "recordings" / f"{identifier}.json"


def load_recording(identifier, sha256=None):
    raw = recording_path(identifier).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if sha256 and digest != sha256:
        raise ValueError("traffic recording checksum mismatch")
    result = json.loads(raw)
    if (
        not isinstance(result, dict)
        or result.get("version") != 1
        or not isinstance(result.get("frames"), list)
        or not result["frames"]
    ):
        raise ValueError("invalid traffic recording")
    duration = number(result.get("duration_ms"))
    if (
        duration is None
        or duration < 0
        or result.get("provider") not in {"adsb.lol", "opensky"}
    ):
        raise ValueError("invalid traffic recording metadata")
    previous = -1
    for frame in result["frames"]:
        if not isinstance(frame, dict):
            raise ValueError("invalid traffic frame")
        timestamp = number(frame.get("simulation_time_ms"))
        if timestamp is None or timestamp < previous or timestamp > duration:
            raise ValueError("invalid traffic recording timeline")
        if (
            not isinstance(frame.get("tracks"), list)
            or len(frame["tracks"]) > MAX_TRACKS
        ):
            raise ValueError("invalid traffic frame tracks")
        previous = timestamp
    return {**result, "sha256": digest}


def recording_catalog():
    result = []
    for path in (data_root() / "recordings").glob("*.json"):
        try:
            data = load_recording(path.stem)
            result.append(
                {
                    k: data[k]
                    for k in (
                        "id",
                        "title",
                        "sha256",
                        "scene_id",
                        "scene_sha256",
                        "duration_ms",
                        "provider",
                    )
                }
            )
        except (ValueError, OSError, KeyError):
            continue
    return result
