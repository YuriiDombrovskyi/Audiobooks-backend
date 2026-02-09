from jose import jwt
from datetime import datetime, timedelta, UTC
from config import JWT_SECRET, JWT_ALGORITHM

def create_jwt(user_id: str):
    payload = {
        "sub": user_id,
        "exp": datetime.now(UTC) + timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
