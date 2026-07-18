from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine

# Import the routers
from routers import (
    entities,
    entity_names,
    entity_people,
    entity_relationships,
    entity_sources,
    relationship_sources,
    relations_type,
)


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

# Include all your API routers
# The prefix and tags are already defined within each routers file
app.include_router(entities.router)
app.include_router(entity_names.router)
app.include_router(entity_people.router)
app.include_router(entity_relationships.router)
app.include_router(entity_sources.router)
app.include_router(relationship_sources.router)
app.include_router(relations_type.router)


# root endpoints to confirm API is running
@app.get("/")
def root():
    return {"name": settings.APP_NAME, "message": "Sankofa System", "status": "Ok"}
