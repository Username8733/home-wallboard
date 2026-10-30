"""Device-local private photo connections. No credentials are returned to the UI."""

import base64
import hashlib
import hmac
import itertools
import json
import logging
import re
import secrets
import shutil
import threading
import time
import uuid
from urllib.parse import urlencode, urlparse

import requests

GOOGLE_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"
GOOGLE_API = "https://photospicker.googleapis.com/v1"
CALLBACK = "http://127.0.0.1:8090/api/photos/google/callback"
MAX_IMAGE = 25 * 1024 * 1024


def private_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.chmod(0o600)
    tmp.replace(path)


def read_json(path, fallback):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return fallback


def image_bytes(response):
    """Bound downloads even when the remote server omits Content-Length."""
    with response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_IMAGE:
                raise ValueError("Bilden är större än 25 MB.")
            chunks.append(chunk)
        return b"".join(chunks)


class PrivatePhotos:
    def __init__(self, library):
        self.library = library
        self.root = library.root / "private-photos"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.lock = threading.RLock()
        self.operation_lock = threading.Lock()
        self.apple = None
        self.apple_items = {}
        self.data = read_json(self.root / "connections.json", {})
        self.apple_albums = read_json(self.root / "icloud-albums.json", [])
        self.google_albums = read_json(self.root / "google-albums.json", [])
        self.status = {
            "icloud": {"state": "disconnected"},
            "google": {"state": "connected" if self.data.get("google_token") else "disconnected"},
        }
        self.oauth = None
        self.picker = None
        # Reuse Apple's saved trusted session; never change the user's sharing settings.
        if self.data.get("icloud"):
            self.run("icloud", lambda: self.apple_login(**self.data["icloud"]))

    def save(self):
        private_json(self.root / "connections.json", self.data)

    def set_status(self, source, state, message="", **extra):
        with self.lock:
            self.status[source] = {"state": state, "message": message, **extra}

    def snapshot(self):
        with self.lock:
            return {
                **{key: dict(value) for key, value in self.status.items()},
                "google_configured": bool(self.data.get("google_client")),
            }

    def albums(self):
        with self.lock:
            return {
                "icloud": [dict(a) for a in self.apple_albums],
                "google": [dict(a) for a in self.google_albums],
            }

    def run(self, source, operation):
        if not self.operation_lock.acquire(blocking=False):
            raise ValueError("En fotoanslutning arbetar redan. Vänta tills den är klar.")
        self.set_status(source, "busy", "Arbetar…")

        def worker():
            try:
                operation()
            except Exception:
                # Provider errors can contain account names, tokens or signed image URLs.
                self.set_status(
                    source,
                    "error",
                    "Anslutningen misslyckades. Kontrollera inloggning/API-inställningar och försök igen.",
                )
            finally:
                self.operation_lock.release()

        threading.Thread(target=worker, daemon=True).start()

    def apple_login(self, username, password):
        from pyicloud import PyiCloudService

        if (
            not isinstance(username, str)
            or not 3 <= len(username) <= 254
            or not isinstance(password, str)
            or not 1 <= len(password) <= 1024
        ):
            raise ValueError("Ange Apple-konto och lösenord.")
        # pyicloud can log response bodies on authentication failure. Keep them private.
        logging.getLogger("pyicloud").disabled = True
        for name in list(logging.Logger.manager.loggerDict):
            if name.startswith("pyicloud."):
                logging.getLogger(name).disabled = True
        self.apple = PyiCloudService(
            username,
            password,
            cookie_directory=str(self.root / "apple-session"),
            with_family=False,
            locate=False,
        )
        with self.lock:
            self.data["icloud"] = {"username": username, "password": password}
            self.save()
        if self.apple.requires_2fa:
            self.set_status("icloud", "two_factor", "Ange koden från din betrodda Apple-enhet.")
            return
        if self.apple.requires_2sa:
            raise ValueError("Använd ett Apple-konto med tvåfaktorsautentisering.")
        self.apple_catalog()

    def apple_verify(self, code):
        if not self.apple or not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
            raise ValueError("Ange den sexsiffriga koden.")
        if not self.apple.validate_2fa_code(code):
            self.set_status("icloud", "two_factor", "Koden kunde inte verifieras. Försök igen.")
            return
        if not self.apple.is_trusted_session:
            self.apple.trust_session()
        self.apple_catalog()

    def apple_catalog(self, refresh=False):
        if refresh:
            self.apple.photos.libraries["root"].refresh_albums()
        albums = []
        for album in self.apple.photos.albums:
            name = album.fullname or album.name
            if album.name in {"Hidden", "Recently Deleted", "Videos"}:
                continue
            identity = hashlib.sha256(str(album.id).encode()).hexdigest()[:24]
            albums.append(
                {
                    "id": "private:" + identity,
                    "name": name + " · privat",
                    "private": True,
                    "key": str(album.id),
                }
            )
        with self.lock:
            self.apple_albums = albums
            private_json(self.root / "icloud-albums.json", albums)
        self.set_status("icloud", "connected", "Privata iCloud-album är anslutna.")
        self.library.changed.set()

    def apple_enumerate(self, album):
        if not self.apple or self.apple.requires_2fa:
            raise ValueError("Logga in på iCloud och bekräfta eventuell tvåfaktorskod.")
        record = next((a for a in self.apple_albums if a["id"] == album), None)
        if not record:
            raise ValueError("Välj ett privat iCloud-album.")
        result = []
        self.apple_items = {}
        for item in itertools.islice(self.apple.photos.albums[record["key"]], 1000):
            if item.item_type != "image":
                continue
            identity = str(item.id)
            self.apple_items[identity] = item
            result.append({"id": identity, "private": True, "date": str(item.created)[:10]})
        return result

    def apple_download(self, identity):
        item = self.apple_items[identity]
        version = next(
            (v for v in ("medium", "thumb", "original") if v in item.versions), "original"
        )
        url = item.download_url(version)
        self.library.image_url(url, "icloud")
        return image_bytes(
            self.apple.session.get(url, stream=True, timeout=(5, 30), allow_redirects=False)
        )

    def google_configure(self, body):
        client = body.get("installed", {}) if isinstance(body, dict) else {}
        cid, secret = client.get("client_id"), client.get("client_secret")
        if (
            not isinstance(cid, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com", cid)
            or not isinstance(secret, str)
            or not 1 <= len(secret) <= 500
        ):
            raise ValueError("Välj Googles OAuth-klientfil för typen Desktop app.")
        with self.lock:
            self.data["google_client"] = {"client_id": cid, "client_secret": secret}
            self.data.pop("google_token", None)
            self.save()
        self.set_status("google", "disconnected", "Klientfil sparad. Logga in på Google.")

    def google_start(self):
        with self.lock:
            client = self.data.get("google_client")
            if not client:
                raise ValueError("Lägg först till en OAuth-klientfil för Google Photos Picker API.")
            verifier = secrets.token_urlsafe(48)
            state = secrets.token_urlsafe(32)
            self.oauth = {"verifier": verifier, "state": state, "expires": time.time() + 600}
            params = {
                **client,
                "redirect_uri": CALLBACK,
                "response_type": "code",
                "scope": GOOGLE_SCOPE,
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
                "code_challenge": base64.urlsafe_b64encode(
                    hashlib.sha256(verifier.encode()).digest()
                )
                .decode()
                .rstrip("="),
                "code_challenge_method": "S256",
            }
            params.pop("client_secret")
            return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

    def google_callback(self, state, code):
        with self.lock:
            pending = self.oauth
            if (
                not pending
                or time.time() > pending["expires"]
                or not isinstance(state, str)
                or not hmac.compare_digest(state, pending["state"])
            ):
                raise ValueError(
                    "Inloggningen har gått ut eller saknar giltig verifiering. Försök igen."
                )
            self.oauth = None
            client = dict(self.data["google_client"])
        if not code or len(code) > 3000:
            raise ValueError("Google-inloggningen avbröts.")
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                **client,
                "code": code,
                "code_verifier": pending["verifier"],
                "redirect_uri": CALLBACK,
                "grant_type": "authorization_code",
            },
            timeout=(5, 20),
        )
        r.raise_for_status()
        token = r.json()
        if not token.get("access_token"):
            raise ValueError("Google-inloggningen gav ingen behörighet.")
        token["expires_at"] = time.time() + token.get("expires_in", 3600)
        with self.lock:
            self.data["google_token"] = token
            self.save()
        self.set_status("google", "connected", "Inloggad. Välj bilder från ett privat album.")

    def google_token(self):
        with self.lock:
            token = self.data.get("google_token", {})
            if not token:
                raise ValueError("Logga in på Google först.")
            if time.time() > token.get("expires_at", 0) - 60:
                if not token.get("refresh_token"):
                    raise ValueError("Logga in på Google igen.")
                r = requests.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        **self.data["google_client"],
                        "refresh_token": token["refresh_token"],
                        "grant_type": "refresh_token",
                    },
                    timeout=(5, 20),
                )
                r.raise_for_status()
                token.update(r.json())
                token["expires_at"] = time.time() + token.get("expires_in", 3600)
                self.save()
            return token["access_token"]

    def google_request(self, method, path, **kwargs):
        response = requests.request(
            method,
            GOOGLE_API + path,
            headers={"Authorization": "Bearer " + self.google_token()},
            timeout=(5, 25),
            **kwargs,
        )
        response.raise_for_status()
        return response

    def google_picker(self, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Ge det privata urvalet ett albumnamn.")
        if self.picker:
            raise ValueError("Avsluta eller avbryt det pågående bildurvalet först.")
        response = self.google_request(
            "POST", "/sessions", json={"pickingConfig": {"maxItemCount": "1000"}}
        ).json()
        uri = response["pickerUri"]
        parsed = urlparse(uri)
        if parsed.scheme != "https" or parsed.hostname != "photos.google.com":
            raise ValueError("Google gav en oväntad urvalsadress.")
        raw_interval = response.get("pollingConfig", {}).get("pollInterval", "5s")
        interval = max(5, min(120, float(raw_interval.rstrip("s"))))
        self.picker = {
            "id": response["id"],
            "name": name.strip(),
            "uri": uri,
            "interval": interval,
            "next_poll": time.time() + interval,
        }
        self.set_status(
            "google",
            "picking",
            "Välj bilder i Google Photos. Återvänd hit och tryck Hämta valda bilder.",
        )
        return parsed._replace(path=parsed.path.rstrip("/") + "/autoclose").geturl()

    def google_import(self):
        picker = self.picker
        if not picker:
            raise ValueError("Starta ett privat bildurval först.")
        if time.time() < picker["next_poll"]:
            self.set_status("google", "picking", "Vänta några sekunder och försök igen.")
            return
        session_path = "/sessions/" + requests.utils.quote(picker["id"], safe="")
        picker["next_poll"] = time.time() + picker["interval"]
        if not self.google_request("GET", session_path).json().get("mediaItemsSet"):
            self.set_status(
                "google", "picking", "Avsluta urvalet i Google Photos innan du hämtar bilderna."
            )
            return
        identity = uuid.uuid4().hex
        folder = self.root / "google-images" / identity
        folder.mkdir(parents=True, mode=0o700)
        count, page = 0, ""
        try:
            while count < 1000:
                body = self.google_request(
                    "GET",
                    "/mediaItems",
                    params={"sessionId": picker["id"], "pageSize": 100, "pageToken": page},
                ).json()
                for item in body.get("mediaItems", []):
                    media = item.get("mediaFile", {})
                    if not media.get("mimeType", "").startswith("image/"):
                        continue
                    url = self.library.image_url(media["baseUrl"], "google") + "=w1920-h1920"
                    data = image_bytes(
                        requests.get(
                            url,
                            headers={"Authorization": "Bearer " + self.google_token()},
                            timeout=(5, 30),
                            stream=True,
                            allow_redirects=False,
                        )
                    )
                    image = self.library.convert(data)
                    (
                        folder / (hashlib.sha256(item["id"].encode()).hexdigest() + ".jpg")
                    ).write_bytes(image)
                    count += 1
                    self.set_status("google", "busy", f"Hämtar privata bilder: {count}")
                    if count >= 1000:
                        break
                page = body.get("nextPageToken", "")
                if not page:
                    break
            if not count:
                raise ValueError("Urvalet innehöll inga bilder.")
            record = {
                "id": "private:" + identity,
                "name": picker["name"] + " · privat urval",
                "private": True,
                "folder": identity,
                "count": count,
            }
            with self.lock:
                self.google_albums.append(record)
                private_json(self.root / "google-albums.json", self.google_albums)
            self.set_status(
                "google",
                "connected",
                f"{count} privata bilder hämtade. Välj albumet och tryck Spara.",
            )
            self.library.changed.set()
            try:
                self.google_request("DELETE", session_path)
            except requests.RequestException:
                pass
            self.picker = None
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    def google_cancel(self):
        if self.picker:
            try:
                self.google_request(
                    "DELETE", "/sessions/" + requests.utils.quote(self.picker["id"], safe="")
                )
            except (requests.RequestException, ValueError):
                pass
            self.picker = None
        self.set_status(
            "google",
            "connected" if self.data.get("google_token") else "disconnected",
            "Bildurvalet är avbrutet.",
        )

    def enumerate(self, source, album):
        if source == "icloud":
            return self.apple_enumerate(album)
        record = next((a for a in self.google_albums if a["id"] == album), None)
        if not record:
            raise ValueError("Välj ett privat Google-urval.")
        folder = self.root / "google-images" / record["folder"]
        return [
            {"id": path.stem, "path": path, "private": True, "date": ""}
            for path in folder.glob("*.jpg")
            if path.is_file() and not path.is_symlink()
        ]

    def download(self, source, item):
        return self.apple_download(item["id"]) if source == "icloud" else item["path"].read_bytes()

    def disconnect(self, source):
        if source not in {"icloud", "google"}:
            raise ValueError("Välj en giltig anslutning.")
        if not self.operation_lock.acquire(blocking=False):
            raise ValueError("Vänta tills fotoanslutningen är klar.")
        try:
            with self.lock:
                if source == "icloud":
                    self.apple = None
                    self.apple_items.clear()
                    self.apple_albums = []
                    self.data.pop("icloud", None)
                    shutil.rmtree(self.root / "apple-session", ignore_errors=True)
                    private_json(self.root / "icloud-albums.json", [])
                else:
                    self.google_cancel()
                    self.data.pop("google_token", None)
                    self.google_albums = []
                    shutil.rmtree(self.root / "google-images", ignore_errors=True)
                    private_json(self.root / "google-albums.json", [])
                self.save()
                self.set_status(
                    source,
                    "disconnected",
                    "Kontot är bortkopplat. Privata bilder tas bort från wallboarden.",
                )
        finally:
            self.operation_lock.release()
