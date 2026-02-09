from cryptography.fernet import Fernet
import os

FERNET_KEY = os.environ["TOKEN_ENCRYPTION_KEY"]
fernet = Fernet(FERNET_KEY)

def encrypt(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()
