"""Authenticated pairing and encrypted, short-lived control messages."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def pairing_proof(secret, device_id, timestamp=None, nonce=None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    nonce = nonce or secrets.token_hex(16)
    value = f"agent/v1|{device_id}|{timestamp}|{nonce}".encode()
    return {
        "timestamp": timestamp,
        "nonce": nonce,
        "signature": hmac.new(secret.encode(), value, hashlib.sha256).hexdigest(),
    }


def verify_proof(secret, device_id, proof, seen, now=None):
    now = time.time() if now is None else now
    timestamp, nonce = proof.get("timestamp"), proof.get("nonce")
    if (
        type(timestamp) is not int
        or not isinstance(nonce, str)
        or len(nonce) != 32
        or abs(now - timestamp) > 60
        or nonce in seen
    ):
        return False
    expected = pairing_proof(secret, device_id, timestamp, nonce)["signature"]
    if not isinstance(proof.get("signature"), str) or not hmac.compare_digest(
        expected, proof["signature"]
    ):
        return False
    for key, stamp in list(seen.items()):
        if now - stamp > 120:
            del seen[key]
    seen[nonce] = now
    return True


def key(secret):
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"home-wallboard/command/v1"
    ).derive(secret.encode())


def seal(secret, device_id, request_id, body, now=None):
    now = time.time() if now is None else now
    data = json.dumps({"issued_at": now, "body": body}, ensure_ascii=False).encode()
    if len(data) > 65536:
        raise ValueError("Command too large")
    nonce = os.urandom(12)
    encrypted = AESGCM(key(secret)).encrypt(nonce, data, f"{device_id}|{request_id}".encode())
    return {
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(encrypted).decode(),
    }


def unseal(secret, device_id, request_id, envelope, now=None):
    now = time.time() if now is None else now
    if not isinstance(envelope, dict) or len(envelope.get("ciphertext", "")) > 100000:
        raise ValueError("Invalid command")
    nonce = base64.b64decode(envelope["nonce"], validate=True)
    data = AESGCM(key(secret)).decrypt(
        nonce,
        base64.b64decode(envelope["ciphertext"], validate=True),
        f"{device_id}|{request_id}".encode(),
    )
    body = json.loads(data)
    if abs(now - body["issued_at"]) > 90 or not isinstance(body["body"], dict):
        raise ValueError("Expired or invalid command")
    return body["body"]
