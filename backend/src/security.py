from hashlib import sha256
import secrets
def hash_password(password: str, salt: str | None = None) -> tuple[str,str]:
    salt=salt or secrets.token_hex(16); return sha256((salt+password).encode()).hexdigest(),salt
def verify_password(password: str,digest: str,salt: str)->bool:
    candidate,_=hash_password(password,salt); return secrets.compare_digest(candidate,digest)
