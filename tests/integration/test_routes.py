import pytest

pytestmark = pytest.mark.integration

def test_home_route(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'Bwb Dashboard' in response.data

def test_search_route(client):
    response = client.get('/search')
    assert response.status_code == 200
    assert b'Bwb Dashboard' in response.data

# def test_queue_position_route(client):
#     response = client.get('/queue_position')
   
# def test_download_route(client):
#     response = client.get('/download_data')

# def test_search_status_route(client):
#     response = client.get('/search/status')
#     assert response.status_code == 200
#     assert b'Bwb Dashboard' in response.data

def test_search_results_route(client):
    response = client.get('/search-results')
    assert response.status_code == 200
    assert b'Bwb Dashboard' in response.data

def test_metadata_route(client):
    response = client.get('/metadata')
    assert response.status_code == 200
    assert b'Bwb Dashboard' in response.data

# test when route should redirect
# def test_create_group_route(client):
#     response = client.get('/create-group')
#     assert response.status_code == 4302
#     assert response.headers['Location'] == '/metadata'

# def test_run_bwb_route(client):
#     response = client.get('/run-bwb')
#     assert response.status_code == 200
#     assert b'Bwb Dashboard' in response.data

def test_bwb_route(client):
    response = client.get('/bwb')
    assert response.status_code == 200
    # assert b'Bwb Dashboard' in response.data

