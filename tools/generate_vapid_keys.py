"""Generate the VAPID key pair for the arena push notifications (קריאה לזירה).

    python tools/generate_vapid_keys.py

Prints VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY ready to paste into Railway's variables.
Generate once: a new pair invalidates every existing browser subscription.
Uses `cryptography`, which `pywebpush` brings along.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate() -> tuple[str, str]:
    """(public, private): the uncompressed P-256 point and the raw 32-byte scalar, base64url."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    private = key.private_numbers().private_value.to_bytes(32, "big")
    return _b64url(public), _b64url(private)


if __name__ == "__main__":
    public_key, private_key = generate()
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print("VAPID_SUBJECT=mailto:<your contact address>")
