import pytest
from web.apis import sra_web_api
import pandas as pd

pytestmark = pytest.mark.unit

def test_get_library_strategy_for_gse_ids_success(mocker):
    mock_sra_web = mocker.patch('web.apis.sra_web_api.SRAweb')
    mock_instance = mock_sra_web.return_value

    srp_data = {
        "study_alias": {
            "0": "GSE"
        },
        "study_accession": {
            "0": "SRP"
        }
    }
    sra_metadata_data = {
        "run_accession": {
            "0": "SRR",
            "1": "SRR"
        },
        "library_layout": {
            "0": "PAIRED",
            "1": "PAIRED",
        },
        "library_strategy": {
            "1": "RNA-Seq",
            "0": "RNA-Seq"
        }
    }
    mock_instance.gse_to_srp.return_value = pd.DataFrame(srp_data)
    mock_instance.sra_metadata.return_value = pd.DataFrame(sra_metadata_data)

    result = sra_web_api.get_library_strategy_for_gse_ids(['GSE1', 'GSE2'])
    assert result == {'GSE1': 'Bulk', 'GSE2': 'Bulk'}

def test_get_metadata_for_gse_ids_success(mocker):
    mock_sra_web = mocker.patch('web.apis.sra_web_api.SRAweb')
    mock_instance = mock_sra_web.return_value

    srp_data = {
        "study_alias": {
            "0": "GSE"
        },
        "study_accession": {
            "0": "SRP"
        }
    }
    sra_metadata_data = {
        "run_accession": {
            "0": "SRR",
            "1": "SRR"
        },
        "experiment_desc": {
            "0": "GSM: RNA-Seq",
            "1": "GSM: RNA-Seq",
        },
        "source_name": {
            "0": "Source name",
            "1": "Source name",
        },
        "library_layout": {
            "0": "PAIRED",
            "1": "PAIRED",
        }
    }
    mock_instance.gse_to_srp.return_value = pd.DataFrame(srp_data)
    mock_instance.sra_metadata.return_value = pd.DataFrame(sra_metadata_data)

    result = sra_web_api.get_metadata_for_gse_ids(['GSE', 'GSE'], save_to_file=False)
    assert isinstance(result, list)
    if isinstance(result, list):
        assert len(result) == 2
        for item in result:
            assert isinstance(item, pd.DataFrame)