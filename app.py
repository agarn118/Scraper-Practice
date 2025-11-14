import os
from flask import Flask, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Serve everything from the project root as "static"
app = Flask(
    __name__,
    static_folder=BASE_DIR,
    static_url_path=""
)

@app.route("/")
def index():
    # Serve index.html from the project root
    return send_from_directory(BASE_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
 