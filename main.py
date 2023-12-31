import binascii
from hashlib import pbkdf2_hmac
from typing import Annotated, Union
from datetime import datetime, timedelta

from Crypto.Cipher import AES
from fastapi import Depends, FastAPI, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware

import crud
import models
import schemas
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)
app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


origins = [
    "http://localhost:63342",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

nonce = b'\xd1\xbb\xed\xbe`O\x8es\t\xad\xff \xe3\xcb}$'

class User(BaseModel):
    username: str
    email: str


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    user = token
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@app.post("/test/")
async def root(current_user: Annotated[User, Depends(get_current_user)], password_name: str,
               db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=str(current_user))
    password_name = password_name.lower()
    password_name = password_name.strip()
    return crud.delete_user_password(db=db, password_name=password_name, user_id=user.id)


@app.post("/token")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    if not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    key = pbkdf2_hmac("sha256", form_data.password.encode(), form_data.username.encode(), 100000, 16)
    key = list(key)
    key = ' '.join(str(e) for e in key)
    return {"access_token": user.email, "token_type": "bearer", 'key': key}

@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user, password=pwd_context.hash(user.password))


@app.post("/users/passwords/", response_model=schemas.Password)
def create_password_for_user(current_user: Annotated[User, Depends(get_current_user)], password: schemas.PasswordCreate,
                             key: str, db: Session = Depends(get_db)):
    b_key = []
    for i in key.split():
        b_key.append(int(i))


    user = crud.get_user_by_email(db, email=str(current_user))
    cipher = AES.new(bytes(b_key), AES.MODE_EAX, nonce=nonce)
    password.password = cipher.encrypt(password.password.encode("utf-8"))
    password.password = binascii.b2a_hex(password.password).decode("utf-8").strip()
    password.name = password.name.strip()
    password.name = password.name.lower()
    return crud.create_user_password(db=db, password=password, user_id=user.id)


@app.post("/password_delete/")
def delete_password_for_user(current_user: Annotated[User, Depends(get_current_user)], password_name: str,
                             db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=str(current_user))
    password_name = password_name.lower()
    password_name = password_name.strip()
    return crud.delete_user_password(db=db, password_name=password_name, user_id=user.id)


@app.post("/passwords/")
def read_passwords(current_user: Annotated[User, Depends(get_current_user)], password_name: str, key: str,
                   db: Session = Depends(get_db)):
    b_key = []
    for i in key.split():
        b_key.append(int(i))

    user = crud.get_user_by_email(db, email=str(current_user))
    password_name = password_name.lower()
    password_name = password_name.strip()
    passwords = crud.get_passwords(db, password_name=password_name, user_id=user.id)
    for password in passwords:
        password.password = binascii.a2b_hex(password.password)
        cipher = AES.new(bytes(b_key), AES.MODE_EAX, nonce=nonce)
        password.password = str(cipher.decrypt(password.password).decode())
    return passwords
