"""Selected-album slideshow sources. Shared links stay in a private device-local store."""

import datetime
import hashlib
import io
import json
import pathlib
import re
import threading
import time
import uuid
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, ImageOps
from private_photos import PrivatePhotos

SOURCES = {
    "immich": "Immich",
    "local": "Lokal mapp",
    "icloud": "iCloud Photos",
    "google": "Google Photos",
}
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class PhotoLibrary:
    def __init__(self, config, settings, cache, root="/var/lib/wallboard"):
        self.c = config
        self.settings = settings
        self.cache = pathlib.Path(cache)
        self.root = pathlib.Path(root)
        self.local = self.root / "local-photos"
        self.links_file = self.root / "photo-sources.json"
        self.lock = threading.RLock()
        self.changed = threading.Event()
        self.catalog = []
        self.catalog_time = 0
        self.immich_online = True
        self.status = {}
        self.links = []
        self.on_progress = None
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.local / "Wallboard").mkdir(parents=True, exist_ok=True)
        try:
            self.links = json.loads(self.links_file.read_text())
        except (OSError, ValueError):
            pass
        self.private = PrivatePhotos(self)

    def key(self, cfg=None):
        cfg = cfg or self.settings.snapshot()
        return cfg.get("photo_source", "immich"), cfg.get("photo_album", "default")

    def manifest(self, key):
        return self.cache / (
            "manifest-" + hashlib.sha256("|".join(key).encode()).hexdigest()[:24] + ".json"
        )

    def cached(self, key=None):
        key = key or self.key()
        p = self.manifest(key)
        if not p.exists() and key == ("immich", "default"):
            p = self.cache / "manifest.json"
        try:
            return [x for x in json.loads(p.read_text()) if (self.cache / x["file"]).is_file()]
        except (OSError, ValueError, KeyError):
            return []

    def im(self, path, params=None):
        r = requests.get(
            self.c["immich_url"] + "/api" + path,
            headers={"x-api-key": self.c["immich_api_key"]},
            params=params,
            timeout=(5, 25),
        )
        r.raise_for_status()
        return r

    def options(self, force=False, allow_refresh=True):
        if allow_refresh and (force or time.time() - self.catalog_time > 300):
            try:
                albums = self.im("/albums").json()
                self.catalog = [
                    {"id": a["id"], "name": a.get("albumName", "Album")} for a in albums
                ]
                self.immich_online = True
            except (requests.RequestException, ValueError, KeyError):
                self.immich_online = False
            self.catalog_time = time.time()
        default_name = next(
            (a["name"] for a in self.catalog if a["id"] == self.c["album_id"]), "Wallboard"
        )
        albums = {
            "immich": [{"id": "default", "name": default_name + " (standard)"}]
            + [x for x in self.catalog if x["id"] != self.c["album_id"]],
            "local": [],
            "icloud": [],
            "google": [],
        }
        for folder in sorted(self.local.iterdir(), key=lambda x: x.name.casefold()):
            if folder.is_dir() and not folder.is_symlink():
                albums["local"].append({"id": self.folder_id(folder), "name": folder.name})
        with self.lock:
            for link in self.links:
                albums[link["source"]].append({"id": link["id"], "name": link["name"]})
            status = dict(self.status)
        for source, private_albums in self.private.albums().items():
            albums[source].extend(
                {"id": a["id"], "name": a["name"], "private": True} for a in private_albums
            )
        return {
            "sources": SOURCES,
            "albums": albums,
            "status": status,
            "immich_online": self.immich_online,
            "connections": self.private.snapshot(),
        }

    @staticmethod
    def folder_id(path):
        return hashlib.sha256(path.name.encode()).hexdigest()[:24]

    def local_folder(self, album):
        for p in self.local.iterdir():
            if p.is_dir() and not p.is_symlink() and self.folder_id(p) == album:
                return p
        raise ValueError("Välj en lokal mapp från listan.")

    def validate_selection(self, cfg):
        source, album = self.key(cfg)
        if source not in SOURCES or not any(
            x["id"] == album for x in self.options()["albums"][source]
        ):
            raise ValueError("Lägg till och välj ett album för bildkällan innan du sparar.")

    def create_folder(self, name):
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[\w ÅÄÖåäö().-]{1,70}", name)
            or name in {".", ".."}
        ):
            raise ValueError("Ange ett mappnamn med bokstäver eller siffror.")
        folder = self.local / name
        if folder.is_symlink():
            raise ValueError("Mappen kan inte användas.")
        folder.mkdir(exist_ok=True)
        return {"id": self.folder_id(folder), "name": folder.name}

    def upload(self, album, uploads):
        folder = self.local_folder(album)
        count = 0
        for upload in uploads:
            data = upload.read(25 * 1024 * 1024 + 1)
            if len(data) > 25 * 1024 * 1024:
                raise ValueError("Varje bild får vara högst 25 MB.")
            image = self.convert(data)
            name = uuid.uuid4().hex + ".jpg"
            (folder / name).write_bytes(image)
            count += 1
        if not count:
            raise ValueError("Välj minst en JPEG-, PNG- eller WebP-bild.")
        self.changed.set()
        return count

    @staticmethod
    def convert(data):
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 50_000_000:
                    raise ValueError("Bilden är för stor.")
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((1920, 1920))
                out = io.BytesIO()
                image.save(out, "JPEG", quality=88)
                return out.getvalue()
        except (OSError, Image.DecompressionBombError):
            raise ValueError("Bilden kunde inte läsas. Använd JPEG, PNG eller WebP.")

    @staticmethod
    def check_link(source, url):
        if not isinstance(url, str) or len(url) > 3000:
            raise ValueError("Ange albumets delningslänk.")
        p = urlparse(url)
        if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
            raise ValueError("Använd en HTTPS-delning från vald bildtjänst.")
        if (
            source == "google"
            and p.hostname in {"photos.app.goo.gl", "photos.google.com"}
            and (p.hostname == "photos.app.goo.gl" or p.path.startswith("/share/"))
        ):
            return url
        if (
            source == "icloud"
            and p.hostname in {"www.icloud.com", "icloud.com"}
            and re.fullmatch(r"/sharedalbum(?:/[a-z]{2}-[a-z]{2})?/?", p.path)
            and re.fullmatch(r"[ABCD][A-Za-z0-9]{7,120}", p.fragment)
        ):
            return url
        raise ValueError(
            "Använd en albumlänk från iCloud Delade album eller Google Photos delade album."
        )

    @staticmethod
    def image_url(url, source):
        p = urlparse(url)
        host = p.hostname or ""
        allowed = (
            bool(re.fullmatch(r"lh\d+\.googleusercontent\.com", host))
            if source == "google"
            else bool(re.fullmatch(r"[a-zA-Z0-9.-]+\.(?:icloud-content\.com|icloud\.com)", host))
        )
        if (
            p.scheme != "https"
            or p.username
            or p.password
            or p.port not in (None, 443)
            or not allowed
        ):
            raise ValueError("Bildtjänsten gav en oväntad bildadress.")
        return url

    def public_get(self, url, source):
        for _ in range(4):
            self.check_link(source, url)
            r = requests.get(
                url,
                timeout=(5, 25),
                allow_redirects=False,
                headers={"User-Agent": "Mozilla/5.0 Wallboard/1.0"},
            )
            if r.status_code in {301, 302, 303, 307, 308}:
                url = urljoin(url, r.headers.get("Location", ""))
                continue
            r.raise_for_status()
            return r
        raise ValueError("Delningslänken kunde inte öppnas.")

    @staticmethod
    def google_items(text):
        """Read image tuples from Google's own shared-album page data, never executable JS."""
        found = {}
        decoder = json.JSONDecoder()

        def visit(node):
            if not isinstance(node, list):
                return
            if (
                len(node) > 1
                and isinstance(node[0], str)
                and isinstance(node[1], list)
                and len(node[1]) >= 3
            ):
                image = node[1]
                if (
                    isinstance(image[0], str)
                    and image[0].startswith("https://lh")
                    and "googleusercontent.com/" in image[0]
                    and all(type(x) in (int, float) for x in image[1:3])
                    and min(image[1:3]) >= 200
                ):
                    found.setdefault(node[0], {"id": node[0], "url": image[0], "date": ""})
            for child in node:
                visit(child)

        for match in re.finditer(r"\bdata:\s*(\[)", text):
            try:
                data, _ = decoder.raw_decode(text[match.start(1) :])
                visit(data)
            except (ValueError, RecursionError):
                continue
        return list(found.values())

    def shared_items(self, source, url):
        self.check_link(source, url)
        if source == "google":
            r = self.public_get(url, source)
            items = self.google_items(r.text)
            for item in items:
                item["url"] = self.image_url(item["url"], source)
            if not items:
                raise ValueError(
                    "Albumet innehåller inga läsbara bilder. Kontrollera att delningslänken är aktiv."
                )
            return items[:1000]
        token = urlparse(url).fragment
        alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        part = token[1] if token[0] == "A" else token[1:3]
        number = 0
        for c in part:
            number = number * 62 + alphabet.index(c)
        host = f"p{number:02d}-sharedstreams.icloud.com"

        def apple(method, payload):
            nonlocal host
            for _ in range(3):
                if not re.fullmatch(r"p\d{2,4}-sharedstreams\.icloud\.com", host):
                    raise ValueError("iCloud gav en oväntad serveradress.")
                r = requests.post(
                    "https://" + host + "/" + token + "/sharedstreams/" + method,
                    json=payload,
                    timeout=(5, 25),
                    allow_redirects=False,
                )
                if r.status_code == 330:
                    host = r.json().get("X-Apple-MMe-Host", "")
                    continue
                r.raise_for_status()
                return r.json()
            raise ValueError("iCloud-albumet kunde inte öppnas.")

        stream = apple("webstream", {"streamCtag": None})
        photos = [x for x in stream.get("photos", []) if x.get("mediaAssetType") != "video"][:1000]
        result = []
        for start in range(0, len(photos), 100):
            group = photos[start : start + 100]
            assets = apple("webasseturls", {"photoGuids": [x["photoGuid"] for x in group]})
            for photo in group:
                variants = [x for x in photo.get("derivatives", {}).values() if x.get("checksum")]
                if not variants:
                    continue
                variant = max(
                    variants, key=lambda x: int(x.get("width", 0)) * int(x.get("height", 0))
                )
                asset = assets.get("items", {}).get(variant["checksum"], {})
                location = assets.get("locations", {}).get(str(asset.get("url_location")), {})
                hosts = location.get("hosts", [])
                if not hosts or not asset.get("url_path"):
                    continue
                image = "https://" + hosts[0] + asset["url_path"]
                result.append(
                    {
                        "id": photo["photoGuid"],
                        "url": self.image_url(image, source),
                        "date": (photo.get("dateCreated") or "")[:10],
                    }
                )
        if not result:
            raise ValueError(
                "Albumet innehåller inga läsbara bilder. Kontrollera albumets webbdelning."
            )
        return result

    def add_shared(self, source, name, url):
        if source not in {"icloud", "google"}:
            raise ValueError("Välj iCloud Photos eller Google Photos.")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Ange ett namn för albumet.")
        self.check_link(source, url)
        items = self.shared_items(source, url)
        record = {"id": uuid.uuid4().hex, "source": source, "name": name.strip(), "url": url}
        with self.lock:
            if len(self.links) >= 30:
                raise ValueError("Högst 30 delade album kan läggas till.")
            self.links.append(record)
            tmp = self.links_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.links, ensure_ascii=False))
            tmp.chmod(0o600)
            tmp.replace(self.links_file)
        return {"id": record["id"], "name": record["name"], "count": len(items)}

    def enumerate(self, key):
        source, album = key
        if source == "local":
            folder = self.local_folder(album)
            return [
                {
                    "id": hashlib.sha256((str(p) + str(p.stat().st_mtime_ns)).encode()).hexdigest(),
                    "path": p,
                    "date": datetime.date.fromtimestamp(p.stat().st_mtime).isoformat(),
                }
                for p in sorted(folder.iterdir())
                if p.suffix.lower() in EXTENSIONS and p.is_file() and not p.is_symlink()
            ]
        if source in {"icloud", "google"} and album.startswith("private:"):
            return self.private.enumerate(source, album)
        if source in {"icloud", "google"}:
            with self.lock:
                record = next(
                    (x for x in self.links if x["source"] == source and x["id"] == album), None
                )
            if not record:
                raise ValueError("Lägg till och välj ett delat album i inställningarna.")
            return self.shared_items(source, record["url"])
        album = self.c["album_id"] if album == "default" else album
        buckets = self.im("/timeline/buckets", {"albumId": album}).json()
        items = []
        for bucket in buckets:
            b = self.im(
                "/timeline/bucket", {"albumId": album, "timeBucket": bucket["timeBucket"]}
            ).json()
            for i, aid in enumerate(b["id"]):
                if not b["isImage"][i] or b["isTrashed"][i]:
                    continue
                items.append(
                    {
                        "id": aid,
                        "date": b["fileCreatedAt"][i][:10],
                        "city": b.get("city", [None] * len(b["id"]))[i] or "",
                    }
                )
        return items

    def refresh(self, key=None):
        key = key or self.key()
        source, album = key
        self.options()
        items = self.enumerate(key)
        result = []
        prior_count = len(self.cached(key))
        for item in items[:1000]:
            if key != self.key():
                return self.cached(key)
            name = hashlib.sha256(("|".join(key) + "|" + item["id"]).encode()).hexdigest() + ".jpg"
            dst = self.cache / name
            if not dst.exists():
                if item.get("private"):
                    data = self.private.download(source, item)
                elif source == "immich":
                    data = self.im(
                        "/assets/" + item["id"] + "/thumbnail", {"size": "preview"}
                    ).content
                elif source == "local":
                    if item["path"].stat().st_size > 25 * 1024 * 1024:
                        continue
                    data = item["path"].read_bytes()
                else:
                    url = self.image_url(item["url"], source)
                    r = requests.get(url, timeout=(5, 25), allow_redirects=False, stream=True)
                    if r.status_code != 200 or not r.headers.get("Content-Type", "").startswith(
                        "image/"
                    ):
                        continue
                    pieces = []
                    size = 0
                    for chunk in r.iter_content(65536):
                        size += len(chunk)
                        if size > 25 * 1024 * 1024:
                            r.close()
                            raise ValueError("En bild i albumet är för stor.")
                        pieces.append(chunk)
                    r.close()
                    data = b"".join(pieces)
                try:
                    converted = self.convert(data)
                except ValueError:
                    continue
                tmp = dst.with_suffix(".tmp")
                tmp.write_bytes(converted)
                tmp.replace(dst)
            result.append(
                {
                    "id": source + ":" + item["id"],
                    "file": name,
                    "date": item.get("date", ""),
                    "city": item.get("city", ""),
                }
            )
            if (
                key == self.key()
                and len(result) > prior_count
                and (len(result) in {1, 5} or len(result) % 20 == 0)
            ):
                self.save_manifest(key, result)
                with self.lock:
                    self.status = {
                        "source": source,
                        "source_name": SOURCES[source],
                        "album": album,
                        "online": True,
                        "loading": True,
                        "updated": time.time(),
                        "count": len(result),
                        "error": "",
                    }
                if self.on_progress:
                    self.on_progress(key, list(result))
        if key != self.key():
            return self.cached(key)
        self.save_manifest(key, result)
        self.prune_cache(key)
        with self.lock:
            self.status = {
                "source": source,
                "source_name": SOURCES[source],
                "album": album,
                "online": True,
                "updated": time.time(),
                "count": len(result),
                "error": "",
            }
        return result

    def save_manifest(self, key, result):
        p = self.manifest(key)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(result))
        tmp.replace(p)

    def prune_cache(self, key):
        legacy = self.cache / "manifest.json"
        if key == ("immich", "default") and legacy.exists():
            legacy.unlink()
        used = set()
        for manifest in self.cache.glob("manifest*.json"):
            try:
                used.update(x["file"] for x in json.loads(manifest.read_text()))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        for image in self.cache.glob("*.jpg"):
            if image.name not in used and time.time() - image.stat().st_mtime > 600:
                image.unlink()

    def failure(self, key):
        if key != self.key():
            return
        with self.lock:
            self.status = {
                "source": key[0],
                "source_name": SOURCES[key[0]],
                "album": key[1],
                "online": False,
                "count": len(self.cached(key)),
                "error": "Bildkällan kunde inte uppdateras. Sparade bilder från valt album visas när de finns.",
            }

    def snapshot(self):
        with self.lock:
            return dict(self.status)
