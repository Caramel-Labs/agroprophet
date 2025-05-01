from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Instantiate FastAPI application
app = FastAPI(
    title="AgroProphet",
    description="AgroProphet - Cold Storage Solution.",
)

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


# Root route (to test service health)
@app.get("/", tags=["Internals"])
async def root():
    return {
        "message": "AgroProphet is up and running! Navigate to /docs to view the SwaggerUI.",
    }
