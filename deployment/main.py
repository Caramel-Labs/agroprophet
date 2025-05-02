# main.py

import sqlite3
from fastapi import FastAPI
from settings import DB_PATH
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from routes.data import router as data_router
from fastapi.middleware.cors import CORSMiddleware
from routes.prediction import router as prediction_router

# ***************************************
#             APPLICATION
# ***************************************


# Instantiate main application
app = FastAPI(
    title="AgroProphet",
    description="AgroProphet - Cold Storage Solution.",
)

app.mount("/static", StaticFiles(directory="static"), name="static")

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
#             DATABASE
# ***************************************

def init_db():
    """Initializes the database by creating necessary tables."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Create price table (added 'actual' column and a unique index)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS price (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                region TEXT NOT NULL,
                crop TEXT NOT NULL,
                price REAL NOT NULL,
                actual INTEGER DEFAULT 0, -- 1 for actual, 0 for predicted
                UNIQUE(date, region, crop) -- Ensure only one entry per date, region, crop
            )
            """
        )

        # Create weather table (added a unique index)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                region TEXT NOT NULL,
                rainfall REAL,
                humidity REAL,
                temp REAL,
                UNIQUE(date, region) -- Ensure only one weather entry per date, region
            )
            """
        )

        # --- New table for tracking prediction errors ---
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS prediction_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,           -- The date the actual price was recorded (and prediction was made for)
                region TEXT NOT NULL,
                crop TEXT NOT NULL,
                squared_error REAL NOT NULL,  -- (predicted_price - actual_price)^2
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP -- When this error record was created
            )
            """
        )

        # --- Add indexes for faster querying on the new table ---
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_date_region_crop ON prediction_errors (date, region, crop);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_region_crop ON prediction_errors (region, crop);")
        # ---------------------------------------------------------

        conn.commit()
    print(f"Database initialized at {DB_PATH}")


# Initialize the database on startup
init_db()


# ***************************************
#             CORS CONFIG
# ***************************************


# Define allowed origins for CORS
origins = [
    "*", # Consider restricting this in production
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
#              ROUTES
# ***************************************


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serves the main HTML page."""
    try:
        with open("static/index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>Index.html not found</h1><p>Make sure static/index.html exists.</p>", status_code=404)


# NOTE
# Other routes can be found in the `routes` folder