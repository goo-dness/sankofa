from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


# create the FastAPI application instance
# title and debug mode come from config.py
app = FastAPI(
    title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan, version="1.0"
)

# allows your frontend to talk this API
# origins lists which URLs are allowed to make requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# root endpoints to confirm API is running
@app.get("/")
def root():
    return {"name": settings.APP_NAME, "message": "Sankofa System", "status": "Ok"}
