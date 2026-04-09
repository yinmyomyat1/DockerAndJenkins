import os
import csv
import logging
from flask import Flask, request, render_template_string, redirect, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Use 'mysql-db-dast' as default host for Docker environments
DB_URI = os.getenv("DB_URI", "mysql+pymysql://root:root@localhost:3306/imdb_db")
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

db = SQLAlchemy()

class Movie(db.Model):
    __tablename__ = "movies"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    genre = db.Column(db.String(255), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    rating = db.Column(db.Float, nullable=False)
    director = db.Column(db.String(255), nullable=True)

class ETLService:
    def run(self, filepath: str):
        if not os.path.exists(filepath):
            logging.error(f"File not found: {filepath}")
            return
            
        with open(filepath, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Handle possible key variations in CSV
                title = row.get('Series_Title') or row.get('title')
                rating = row.get('IMDB_Rating') or row.get('rating')
                
                if not title or not rating: continue
                
                try:
                    exists = Movie.query.filter_by(title=title.strip()).first()
                    if not exists:
                        movie = Movie(
                            title=title.strip(),
                            genre=row.get('Genre', 'Unknown').strip(),
                            year=int(row.get('Released_Year', 0)),
                            rating=float(rating),
                            director=row.get('Director', 'Unknown').strip()
                        )
                        db.session.add(movie)
                except Exception as e:
                    logging.warning(f"Error processing row: {e}")
            db.session.commit()
            logging.info("ETL completed successfully.")

def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = DB_URI
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    @app.route("/")
    def home():
        # Simple landing page for the Health Check/DAST
        return "<h1>IMDB App is Running</h1><p><a href='/admin/login'>Admin Login</a></p>"

    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            # Simple hardcoded check for demo purposes
            if request.form["username"] == "admin" and request.form["password"] == "1234":
                session["admin"] = True
                return "Login Successful"
            return "Invalid Credentials", 401
        return '<form method="POST">User: <input name="username"> Pass: <input type="password" name="password"><button>Login</button></form>'

    return app

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        # Ensure data directory exists
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        
        csv_path = os.path.join(DATA_DIR, "imdb_top_1000.csv")
        ETLService().run(csv_path)

    # Note: Running on 5050 to match pipeline expectations
    app.run(host='0.0.0.0', port=5050)
