import pytest
from web import app as flask_app

# Run tests using the command: PYTHONPATH=. pytest

@pytest.fixture()
def app():
    # app.config['TESTING'] = True
    # app.config['WTF_CSRF_ENABLED'] = False
    flask_app.config.update({
        "TESTING": True,
    })
    yield flask_app

@pytest.fixture()
def client(app):
    return app.test_client()