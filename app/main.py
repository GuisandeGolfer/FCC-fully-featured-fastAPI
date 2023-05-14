from fastapi import FastAPI
from . import models
from .database import engine
from .routers import post, user, auth, vote
# from .config import settings

# Don't need anymore due to Alembic setup
# models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(post.router)
app.include_router(user.router)
app.include_router(auth.router)
app.include_router(vote.router)


@app.get('/')
def read_root():
    return {"message": "Welcome to my API"}
