# imdb_etl_mysql_admin_secure.py
import os
import csv
import logging
from typing import List, Dict
from flask import Flask, request, render_template_string, redirect, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------- Logging --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -------------------- Config --------------------
DB_URI = os.getenv("DB_URI", "mysql+pymysql://root@localhost/imdb_db")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", generate_password_hash("1234"))
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

db = SQLAlchemy()

# -------------------- Model --------------------
class Movie(db.Model):
    __tablename__ = "movies"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    genre = db.Column(db.String(255), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    rating = db.Column(db.Float, nullable=False)
    director = db.Column(db.String(255), nullable=True)

# -------------------- ETL Pipeline --------------------
class ETLService:

    def extract(self, filepath: str) -> List[Dict]:
        filepath = os.path.abspath(filepath)
        if not filepath.startswith(DATA_DIR):
            raise PermissionError("Invalid file path")
        if not os.path.exists(filepath):
            raise FileNotFoundError(filepath)
        logging.info(f"Extracting data from {filepath}")
        with open(filepath, encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def transform(self, raw_data: List[Dict]) -> List[Dict]:
        cleaned = []
        for row in raw_data:
            if not row.get('IMDB_Rating'):
                continue
            try:
                cleaned.append({
                    "title": row['Series_Title'].strip(),
                    "genre": row['Genre'].strip(),
                    "year": int(row['Released_Year']),
                    "rating": float(row['IMDB_Rating']),
                    "director": row.get('Director', '').strip()
                })
            except Exception as e:
                logging.warning(f"Skipping row {row}: {e}")
                continue
        logging.info(f"Transformed {len(cleaned)} valid rows")
        return cleaned

    def load(self, data: List[Dict]):
        for d in data:
            exists = Movie.query.filter_by(title=d["title"], year=d["year"]).first()
            if not exists:
                db.session.add(Movie(**d))
        db.session.commit()
        logging.info(f"Loaded {len(data)} movies into DB")

    def run(self, filepath: str):
        raw = self.extract(filepath)
        transformed = self.transform(raw)
        self.load(transformed)

# -------------------- Services --------------------
class MovieService:
    def filter_movies(self, genre, start_year, end_year):
        query = Movie.query
        if genre:
            query = query.filter(Movie.genre.ilike(f"%{genre}%"))
        query = query.filter(Movie.year.between(start_year, end_year))
        return query.all()

    def top_movies(self, movies, limit=5):
        return sorted(movies, key=lambda m: m.rating, reverse=True)[:limit]

class AuthService:
    def login(self, username, password):
        return username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password)

# -------------------- Input Validation --------------------
def validate_movie_form(form):
    try:
        title = form["title"].strip()
        genre = form["genre"].strip()
        director = form.get("director", "").strip()
        year = int(form["year"])
        rating = float(form["rating"])
        if not title or not genre:
            raise ValueError("Title and Genre are required")
        return {"title": title, "genre": genre, "year": year, "rating": rating, "director": director}, None
    except Exception as e:
        return None, str(e)

# -------------------- App Factory --------------------
def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = DB_URI
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax'
    )
    db.init_app(app)

    movie_service = MovieService()
    auth_service = AuthService()

    # -------------------- Templates --------------------
    LOGIN_HTML = """
    <h2>Login</h2>
    <form method="POST">
        UserName<input name="username"><br><br>
        Password<input type="password" name="password"><br><br>
        <button>Login</button>
    </form>
    {% if error %}
    <p style="color:red;">{{ error }}</p>
    {% endif %}
    """

    DASHBOARD_HTML = """
    <h2>Dashboard</h2>
    <a href="/admin/add">Add</a> | <a href="/admin/logout">Logout</a>
    <form method="GET">
        <input name="search" placeholder="Search title">
        <button>Search</button>
    </form>
    <table border="1">
        <tr>
            <th>Title</th><th>Genre</th><th>Year</th><th>Rating</th><th>Action</th>
        </tr>
        {% for m in movies %}
        <tr>
            <td>{{ m.title }}</td>
            <td>{{ m.genre }}</td>
            <td>{{ m.year }}</td>
            <td>{{ m.rating }}</td>
            <td>
                <a href="/admin/edit/{{m.id}}">Edit</a>
                <a href="/admin/delete/{{m.id}}">Delete</a>
            </td>
        </tr>
        {% endfor %}
    </table>
    """

    FORM_HTML = """
    <h2>{{ title }}</h2>
    <form method="POST">
        <input name="title" value="{{ m.title if m else '' }}"><br>
        <input name="genre" value="{{ m.genre if m else '' }}"><br>
        <input name="year" type="number" value="{{ m.year if m else '' }}"><br>
        <input name="rating" type="number" step="0.1" value="{{ m.rating if m else '' }}"><br>
        <input name="director" value="{{ m.director if m else '' }}"><br>
        <button>Save</button>
    </form>
    <p>{{ msg }}</p>
    """

    # -------------------- Auth --------------------
    def is_admin():
        return session.get("admin") is True

    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            if auth_service.login(request.form["username"], request.form["password"]):
                session["admin"] = True
                return redirect("/admin/dashboard")
            else:
                error = "Invalid login"
        return render_template_string(LOGIN_HTML, error=error)

    @app.route("/admin/logout")
    def logout():
        session.clear()
        return redirect("/admin/login")

    # -------------------- Dashboard --------------------
    @app.route("/admin/dashboard")
    def dashboard():
        if not is_admin():
            return redirect("/admin/login")
        search = request.args.get("search")
        movies = Movie.query.filter(Movie.title.ilike(f"%{search}%")).all() if search else Movie.query.all()
        return render_template_string(DASHBOARD_HTML, movies=movies)

    # -------------------- Create --------------------
    @app.route("/admin/add", methods=["GET", "POST"])
    def add():
        if not is_admin():
            return redirect("/admin/login")
        msg = None
        if request.method == "POST":
            movie_data, error = validate_movie_form(request.form)
            if movie_data:
                db.session.add(Movie(**movie_data))
                db.session.commit()
                msg = "Added!"
                logging.info(f"Admin added movie: {movie_data}")
            else:
                msg = f"Error: {error}"
        return render_template_string(FORM_HTML, title="Add Movie", m=None, msg=msg)

    # -------------------- Update --------------------
    @app.route("/admin/edit/<int:id>", methods=["GET", "POST"])
    def edit(id):
        if not is_admin():
            return redirect("/admin/login")
        m = Movie.query.get_or_404(id)
        msg = None
        if request.method == "POST":
            movie_data, error = validate_movie_form(request.form)
            if movie_data:
                for key, value in movie_data.items():
                    setattr(m, key, value)
                db.session.commit()
                msg = "Updated!"
                logging.info(f"Admin updated movie: {movie_data}")
            else:
                msg = f"Error: {error}"
        return render_template_string(FORM_HTML, title="Edit Movie", m=m, msg=msg)

    # -------------------- Delete --------------------
    @app.route("/admin/delete/<int:id>")
    def delete(id):
        if not is_admin():
            return redirect("/admin/login")
        m = Movie.query.get_or_404(id)
        logging.info(f"Admin deleted movie: {m.title} ({m.year})")
        db.session.delete(m)
        db.session.commit()
        return redirect("/admin/dashboard")

    # -------------------- Public Recommendation --------------------
    @app.route("/", methods=["GET", "POST"])
    def home():
        movies = []
        if request.method == "POST":
            try:
                genre = request.form.get("genre", "").strip()
                start = int(request.form["start"])
                end = int(request.form["end"])
                filtered = movie_service.filter_movies(genre, start, end)
                movies = movie_service.top_movies(filtered)
            except Exception as e:
                logging.warning(f"Error filtering movies: {e}")
        return render_template_string("""
            <h2>Recommend</h2>
            <form method="POST">
                Genre: <input name="genre"><br><br>
                Start date: <input name="start" type="number"><br><br>
                End date: <input name="end" type="number"><br><br>
                <button>Search</button>
            </form>
            {% if movies %}
                <ul>
                {% for m in movies %}
                    <li>{{m.title}} ({{m.year}}) - {{m.rating}}</li>
                {% endfor %}
                </ul>
            {% else %}
                <p>No movies found</p>
            {% endif %}
        """, movies=movies)

    return app

# -------------------- Bootstrap --------------------
def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        # Run ETL securely
        csv_path = os.path.join(DATA_DIR, "imdb_top_1000.csv")
        etl = ETLService()
        try:
            etl.run(csv_path)
        except Exception as e:
            logging.error(f"ETL failed: {e}")

    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()
