import os

# Database path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "mydatabase.db") # Adjust path as needed

# Models path
MODELS_PATH = os.path.join(BASE_DIR, "models") # Adjust path as needed


# --- Settings for RMSE Tracking ---
# RMSE threshold for triggering retraining
# Adjust this value based on acceptable error levels for your application
RMSE_THRESHOLD = 10.0 

# Minimum number of error points required in the rolling window
# to calculate RMSE and trigger retraining check
MIN_ERROR_POINTS = 10 



# Database settings
DB_PATH = "agroprophet.db"

# Models settings
MODELS_PATH = "models"

# Data definitions

FRUITS = {
    "Plantain",
    "Loquat",
    "Cantaloupe",
    "Starfruit",
    "Bael Fruit",
    "Indian Gooseberry (Amla)",
    "Dragon Fruit",
    "Pulasan",
    "Feijoa",
    "Langsat",
    "Sapodilla",
    "Breadnut",
    "Cherimoya",
    "Atemoya",
    "Red Currant",
    "Tangerine",
    "Cranberry",
}

VEGETABLES = {
    "Snow Peas",
    "Bottle Gourd",
    "White Eggplant",
    "Thai Eggplant",
    "Watercress",
    "Amaranth Leaves",
    "Spring Onion",
    "Gotu Kola",
    "Parsnip",
    "Napa Cabbage",
    "Turnip",
    "Rutabaga",
    "Butternut Squash",
    "Shallot",
    "Sweet Potato",
    "Durian",
    "Green Banana",
    "Okra",
    "Cassava",
    "Yam",
}
