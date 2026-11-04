"""Project-wide settings and the Delhi NCR locality reference table."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "realestate.db"
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "price_model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"

# Canonical localities. Coordinates are approximate centre points for the map.
# base_ppsf is only used by the synthetic sample generator, never by analysis.
LOCALITIES = [
    # name,                        city,        lat,     lon,     base_ppsf, weekly_trend
    ("DLF Phase 5",                "Gurugram",  28.4425, 77.1027, 22000,  0.0040),
    ("Golf Course Extension Road", "Gurugram",  28.4110, 77.1100, 17000,  0.0055),
    ("Sector 65",                  "Gurugram",  28.4037, 77.0729, 15000,  0.0035),
    ("Sohna Road",                 "Gurugram",  28.4011, 77.0425, 11500,  0.0020),
    ("Dwarka Expressway",          "Gurugram",  28.4880, 76.9990, 12500,  0.0065),
    ("Sector 85",                  "Gurugram",  28.3940, 76.9590,  9500,  0.0030),
    ("Sector 150",                 "Noida",     28.4180, 77.4890, 10500,  0.0050),
    ("Sector 62",                  "Noida",     28.6270, 77.3650,  9000,  0.0010),
    ("Sector 75",                  "Noida",     28.5760, 77.3870,  9800,  0.0015),
    ("Sector 137",                 "Noida",     28.5100, 77.4060,  8500,  0.0025),
    ("Noida Extension",            "Noida",     28.6010, 77.4400,  6000,  0.0045),
    ("Dwarka",                     "Delhi",     28.5921, 77.0460, 13000,  0.0012),
    ("Vasant Kunj",                "Delhi",     28.5293, 77.1530, 21000,  0.0008),
    ("Rohini",                     "Delhi",     28.7380, 77.0820, 12000,  0.0005),
    ("Mayur Vihar",                "Delhi",     28.6100, 77.2950, 13500, -0.0010),
    ("Indirapuram",                "Ghaziabad", 28.6460, 77.3710,  8000,  0.0018),
    ("Raj Nagar Extension",        "Ghaziabad", 28.6930, 77.4300,  5000,  0.0022),
    ("Greater Faridabad",          "Faridabad", 28.4200, 77.3500,  6000, -0.0005),
]

LOCALITY_INFO = {
    name: {"city": city, "lat": lat, "lon": lon}
    for name, city, lat, lon, _b, _t in LOCALITIES
}

# Fictional builder names, so the synthetic data never implies anything about real companies.
BUILDERS = {
    "Aravali Homes": 1.12,
    "Yamuna Developers": 0.95,
    "Skyline Infra": 1.05,
    "Greenfield Estates": 1.00,
    "Metro Realty": 0.92,
    "Orchid Buildcon": 1.18,
    "Resale / Individual": 0.97,
}

STATUSES = ["Ready to Move", "Under Construction"]
