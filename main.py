import sqlite3
from fastapi import FastAPI
from settings import DB_PATH
from routes.data import router as data_router
from fastapi.middleware.cors import CORSMiddleware
from routes.prediction import router as prediction_router

# ***************************************
#              APPLICATION
# ***************************************


# Instantiate main application
app = FastAPI(
    title="AgroProphet",
    description="AgroProphet - Cold Storage Solution.",
)

# Bind routers to main application
app.include_router(
    router=data_router,
    prefix="/api",
)
app.include_router(
    router=prediction_router,
    prefix="/api",
)


# ***************************************
#               DATABASE
# ***************************************


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Create price table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS price (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                region TEXT NOT NULL,
                crop TEXT NOT NULL,
                price REAL NOT NULL
            )
        """
        )
        # Create weather table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                region TEXT NOT NULL,
                rainfall REAL,
                humidity REAL,
                temp REAL
            )
        """
        )
        conn.commit()


init_db()


# ***************************************
#              CORS CONFIG
# ***************************************


# Define allowed origins for CORS
origins = [
    "*",
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:4000",
]

# Setup CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ***************************************
#               ROUTES
# ***************************************


@app.get("/", tags=["Internals"])
async def root():
    return {
        "message": "AgroProphet is up and running! Navigate to /docs to view the SwaggerUI.",
    }


# NOTE
# Other routes can be found in the `routes` folder
