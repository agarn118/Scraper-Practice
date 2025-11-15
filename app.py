import os
from pathlib import Path
from flask import Flask, send_from_directory

BASE_DIR = Path(__file__).resolve().parent

# Frontend (HTML/CSS/JS)
FRONTEND_DIR = BASE_DIR / "frontend"

# Processed data (products.json lives here)
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR),
    static_url_path=""  # so "/" and "/script.js" etc. serve from frontend
)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/products.json")
def products_json():
    # Serve the merged catalog built by tools/build_frontend_json.py
    return send_from_directory(DATA_PROCESSED_DIR, "products.json")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
