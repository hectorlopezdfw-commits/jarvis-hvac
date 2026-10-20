import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_DB',str(tmp_path/'test.sqlite'))
    with TestClient(app,headers={'Origin':'http://testserver','X-Jarvis-Request':'1'}) as c:
        yield c


@pytest.fixture
def owner(client):
    assert client.post('/api/session',json={'actor':'owner'}).status_code==200
    return client
