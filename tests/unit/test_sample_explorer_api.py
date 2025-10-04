import pytest
import requests
from web.apis.sample_explorer_api import SampleExplorerAPI

pytestmark = pytest.mark.unit

def test_create_api_instance():
    sample_explorer = SampleExplorerAPI()
    assert isinstance(sample_explorer, SampleExplorerAPI)

def test_make_query_success(mocker):
    mock_post = mocker.patch('requests.post')

    mock_response = mocker.Mock()
    mock_response.status_code = 202
    mock_response.json.return_value = {"status": "data_retrieved"}
    mock_post.return_value = mock_response

    url = 'http://127.0.0.1:5001/query_rag'
    test_payload = {
        'uuid': 'user123',
        'text_query_used': True,
        'text_query': 'query',
        'gene_set_used': True,
        'gene_set': ['gene'],
        'search': 'semantic',
        'expand': 'semantic'
    }
    data = SampleExplorerAPI().make_query('user123', True, 'query', True, ['gene'], 'semantic', 'semantic')

    assert data == {"status": "data_retrieved"}
    mock_post.assert_called_once_with(url, json=test_payload)

def test_make_query_error(mocker):
    mock_post = mocker.patch('requests.post')

    mock_response = mocker.Mock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "message"}
    mock_post.return_value = mock_response

    url = 'http://127.0.0.1:5001/query_rag'
    test_payload = {
        'uuid': 'user123',
        'text_query_used': True,
        'text_query': 'query',
        'gene_set_used': True,
        'gene_set': ['gene'],
        'search': 'semantic',
        'expand': 'semantic'
    }
    data = SampleExplorerAPI().make_query('user123', True, 'query', True, ['gene'], 'semantic', 'semantic')

    assert data == {"error": "message"}
    mock_post.assert_called_once_with(url, json=test_payload)

def test_make_query_connection_error(mocker):
    mocker.patch(
        'requests.post',
        side_effect=requests.exceptions.ConnectionError
    )

    data = SampleExplorerAPI().make_query('user123', True, 'query', True, ['gene'], 'semantic', 'semantic')

    assert data == {'error': 'Connection error'}

def test_get_queue_position_success(mocker):
    mock_post = mocker.patch('requests.post')

    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "in_progress"}
    mock_post.return_value = mock_response

    url = 'http://127.0.0.1:5001/queue_position'
    data = SampleExplorerAPI().get_queue_position('user123')

    assert data == {"status": "in_progress"}
    mock_post.assert_called_once_with(url, json={'uuid': 'user123'})

def test_get_queue_position_connection_error(mocker):
    mocker.patch(
        'requests.post',
        side_effect=requests.exceptions.ConnectionError
    )

    data = SampleExplorerAPI().get_queue_position('user123')

    assert data == None

def test_get_data_output_success(mocker):
    mock_post = mocker.patch('requests.post')

    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "data_retrieved"}
    mock_post.return_value = mock_response

    url = 'http://127.0.0.1:5001/data_output'
    data = SampleExplorerAPI().get_data_output('user123', 10)

    assert data == {"status": "data_retrieved"}
    mock_post.assert_called_once_with(url, json={'uuid': 'user123', 'amount_of_lines': 10})

def test_get_data_output_error_query_not_present(mocker):
    mock_post = mocker.patch('requests.post')

    mock_response = mocker.Mock()
    mock_response.status_code = 400
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
    mock_post.return_value = mock_response

    url = 'http://127.0.0.1:5001/data_output'
    data = SampleExplorerAPI().get_data_output('user123', 10)

    assert data == None
    mock_post.assert_called_once_with(url, json={'uuid': 'user123', 'amount_of_lines': 10})

def test_get_data_output_connection_error(mocker):
    mocker.patch(
        'requests.post',
        side_effect=requests.exceptions.ConnectionError
    )

    data = SampleExplorerAPI().get_data_output('user123', 10)

    assert data == None

def test_get_download_file():
    pass

def test_get_download_file_connection_error(mocker):
    mocker.patch(
        'requests.post',
        side_effect=requests.exceptions.ConnectionError
    )

    data = SampleExplorerAPI().get_download_file('user123', 10)

    assert data == None