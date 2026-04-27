import pytest
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

# Import your modules (adjust if file name differs)
from Imdb_etl_mysql_admin_secure import (
    ETLService,
    MovieService,
    AuthService,
    validate_movie_form,
    Movie,
    db,
    create_app,
)

# -------------------- FIXTURE: Flask App --------------------
@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


# -------------------- FIXTURE: ETL Service --------------------
@pytest.fixture
def etl():
    return ETLService()


# -------------------- TEST: ETL Extract (NO FILE ERROR) --------------------
@patch("builtins.open", new_callable=MagicMock)
@patch("os.path.exists", return_value=True)
@patch("os.path.abspath", return_value="/app/data/test.csv")
def test_extract(mock_abspath, mock_exists, mock_open, etl):
    mock_open.return_value.__enter__.return_value = [
        {"Series_Title": "Movie A", "Genre": "Action", "Released_Year": "2020", "IMDB_Rating": "8.5"}
    ]

    result = etl.extract("/app/data/test.csv")
    assert mock_open.called


# -------------------- TEST: Transform --------------------
def test_transform(etl):
    raw = [
        {
            "Series_Title": "  Movie A ",
            "Genre": " Action ",
            "Released_Year": "2020",
            "IMDB_Rating": "8.5",
            "Director": "John Doe"
        },
        {
            "Series_Title": "Bad Movie",
            "Genre": "Drama",
            "Released_Year": "not_a_year",
            "IMDB_Rating": "",  # should be skipped
        }
    ]

    result = etl.transform(raw)

    assert len(result) == 1
    assert result[0]["title"] == "Movie A"
    assert result[0]["year"] == 2020


# -------------------- TEST: Auth Service --------------------
def test_auth_success():
    service = AuthService()
    with patch("your_app_file.ADMIN_USERNAME", "admin"):
        with patch("your_app_file.ADMIN_PASSWORD_HASH", generate_password_hash("1234")):
            assert service.login("admin", "1234") is True


def test_auth_fail():
    service = AuthService()
    assert service.login("wrong", "wrong") is False


# -------------------- TEST: Movie Service Filter --------------------
def test_movie_service_filter(app):
    service = MovieService()

    movie = Movie(title="Test Movie", genre="Action", year=2020, rating=9.0)
    db.session.add(movie)
    db.session.commit()

    result = service.filter_movies("Action", 2019, 2021)

    assert len(result) == 1
    assert result[0].title == "Test Movie"


# -------------------- TEST: Top Movies --------------------
def test_top_movies():
    service = MovieService()

    class FakeMovie:
        def __init__(self, title, rating):
            self.title = title
            self.rating = rating

    movies = [
        FakeMovie("A", 7.0),
        FakeMovie("B", 9.5),
        FakeMovie("C", 8.0),
    ]

    result = service.top_movies(movies, limit=2)

    assert result[0].title == "B"
    assert result[1].title == "C"


# -------------------- TEST: Form Validation --------------------
def test_validate_movie_form_valid():
    form = {
        "title": "  Inception ",
        "genre": " Sci-Fi ",
        "year": "2010",
        "rating": "8.8",
        "director": "Nolan"
    }

    data, error = validate_movie_form(form)

    assert error is None
    assert data["title"] == "Inception"
    assert data["year"] == 2010


def test_validate_movie_form_invalid():
    form = {
        "title": "",
        "genre": "",
        "year": "abc",
        "rating": "xyz"
    }

    data, error = validate_movie_form(form)

    assert data is None
    assert error is not None
