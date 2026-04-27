import pytest
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Imdb_etl_mysql_admin_secure import create_app, db, Movie, AuthService, MovieService, ETLService, validate_movie_form
from werkzeug.security import generate_password_hash


# -------------------- Fixtures --------------------

@pytest.fixture
def app():
    app = create_app()

    # Use in-memory SQLite for testing
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        TESTING=True,
        SECRET_KEY="testkey",
        WTF_CSRF_ENABLED=False
    )

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


# -------------------- Auth Tests --------------------

def test_auth_success():
    auth = AuthService()
    assert auth.login("admin", "1234") is True


def test_auth_failure():
    auth = AuthService()
    assert auth.login("wrong", "wrong") is False


# -------------------- Validation Tests --------------------

def test_validate_movie_form_success():
    form = {
        "title": "Inception",
        "genre": "Sci-Fi",
        "year": "2010",
        "rating": "8.8",
        "director": "Nolan"
    }

    data, error = validate_movie_form(form)

    assert error is None
    assert data["title"] == "Inception"
    assert data["year"] == 2010
    assert data["rating"] == 8.8


def test_validate_movie_form_failure():
    form = {
        "title": "",
        "genre": "",
        "year": "abc",
        "rating": "xyz"
    }

    data, error = validate_movie_form(form)

    assert data is None
    assert error is not None


# -------------------- MovieService Tests --------------------

def test_movie_filter_and_top_movies(app):
    with app.app_context():
        m1 = Movie(title="A", genre="Action", year=2000, rating=8.0)
        m2 = Movie(title="B", genre="Action", year=2005, rating=9.0)
        m3 = Movie(title="C", genre="Drama", year=2003, rating=7.0)

        db.session.add_all([m1, m2, m3])
        db.session.commit()

        service = MovieService()
        result = service.filter_movies("Action", 1999, 2010)
        top = service.top_movies(result)

        assert len(result) == 2
        assert top[0].rating == 9.0


# -------------------- ETL Tests --------------------

def test_etl_transform():
    etl = ETLService()

    raw_data = [
        {
            "Series_Title": "Movie A",
            "Genre": "Action",
            "Released_Year": "2001",
            "IMDB_Rating": "8.5",
            "Director": "Dir A"
        },
        {
            "Series_Title": "Bad Movie",
            "Genre": "Drama",
            "Released_Year": "not_year",
            "IMDB_Rating": "",  # should be skipped
            "Director": "Dir B"
        }
    ]

    result = etl.transform(raw_data)

    assert len(result) == 1
    assert result[0]["title"] == "Movie A"
    assert result[0]["year"] == 2001


# -------------------- Flask Route Tests --------------------

def test_login_route(client):
    res = client.post("/admin/login", data={
        "username": "admin",
        "password": "1234"
    }, follow_redirects=True)

    assert res.status_code == 200


def test_login_failure(client):
    res = client.post("/admin/login", data={
        "username": "bad",
        "password": "wrong"
    })

    assert b"Invalid login" in res.data


def test_dashboard_redirect_when_not_logged_in(client):
    res = client.get("/admin/dashboard")
    assert res.status_code in (301, 302)


def test_add_movie_requires_login(client):
    res = client.get("/admin/add")
    assert res.status_code in (301, 302)
