import pytest
from web.utils import utils, sample_explorer_utils

pytestmark = pytest.mark.unit

# UTILS

# @pytest.mark.unit
def test_format_genes_from_str_to_list():
    genes_from_text_area = "MMP8\nLTF\nCAMP\nHP\nDCLK2\nGOLGA8R\nKIR3DL2\nPTPRN2-AS1\nSERPINB9\nB3GAT1"
    result = ["MMP8", "LTF", "CAMP", "HP", "DCLK2", "GOLGA8R", "KIR3DL2", "PTPRN2-AS1", "SERPINB9", "B3GAT1"]
    assert utils.format_genes_from_str_to_list(genes_from_text_area) == result

# SAMPLE EXPLORER UTILS

@pytest.fixture
def unmodified_data():
    data = {
        "data": {
            "expansion_studies": [
                {
                    "gse_id": "GSE1",
                    "gse_id_text": "Text"
                },
                {
                    "gse_id": "GSE1",
                    "gse_id_text": "Text"
                },
                {
                    "gse_id": "GSE9",
                    "gse_id_text": "Text"
                }
            ],
            "samples": [
                {
                    "geo_accession": "GSM9",
                    "series_id": "GSE4"
                },
                {
                    "geo_accession": "GSM0",
                    "series_id": "GSE4"
                },
                {
                    "geo_accession": "GSM1",
                    "series_id": "GSE4"
                }
            ],
            "seed_studies": [
                {
                    "gse_id": "GSE1",
                    "gse_id_text": "Text"
                },
                {
                    "gse_id": "GSE7",
                    "gse_id_text": "Text"
                },
                {
                    "gse_id": "GSE8,GSE9",
                    "gse_id_text": "Text"
                }
            ]
        },
        "status": "data_retrieved"
    }
    return data

def test_get_unique_gse_ids_success(unmodified_data):
    result = sample_explorer_utils.get_unique_gse_ids(unmodified_data)
    result.sort()

    expected = ['GSE1', 'GSE4', 'GSE7', 'GSE8,GSE9', 'GSE9']
    expected.sort()
    assert result == expected

def test_reshape_data_success(unmodified_data):
    result = sample_explorer_utils.reshape_data(unmodified_data)

    expected_result = {
        "data": {
            "expansion_studies": [
                {
                    "gse_id": "GSE1",
                    "gse_id_text": "Text"
                },
                {
                    "gse_id": "GSE9",
                    "gse_id_text": "Text"
                }
            ],
            "samples": [
                {
                    "geo_accession": "GSM9",
                    "series_id": "GSE4"
                },
                {
                    "geo_accession": "GSM0",
                    "series_id": "GSE4"
                },
                {
                    "geo_accession": "GSM1",
                    "series_id": "GSE4"
                }
            ],
            "seed_studies": [
                {
                    "gse_id": "GSE1",
                    "gse_id_text": "Text"
                },
                {
                    "gse_id": "GSE7",
                    "gse_id_text": "Text"
                },
                {
                    "gse_id": "GSE8",
                    "gse_id_text": "Text"
                },
                {
                    "gse_id": "GSE9",
                    "gse_id_text": "Text"
                }
            ]
        },
        "status": "data_retrieved"
    }
    assert result == expected_result

def test_add_sample_type_to_studies_data_success():
    data_samples = {'GSE8': 'Bulk', 'GSE7': 'Single-cell'}
    data_studies = {
        "data": {
            "expansion_studies": [
                {
                    "gse_id": "GSE8"
                }
            ],
            "samples": [
                {
                    "series_id": "GSE4"
                }
            ],
            "seed_studies": [
                {
                    "gse_id": "GSE7"
                }
            ]
        },
        "status": "data_retrieved"
    }
    expected = {
        "data": {
            "expansion_studies": [
                {
                    "gse_id": "GSE8",
                    "sample_type": "Bulk"
                }
            ],
            "samples": [
                {
                    "series_id": "GSE4",
                    "sample_type": ""
                }
            ],
            "seed_studies": [
                {
                    "gse_id": "GSE7",
                    "sample_type": "Single-cell"
                }
            ]
        },
        "status": "data_retrieved"
    }
    result = sample_explorer_utils.add_sample_type_to_studies_data(data_samples, data_studies)
    assert result == expected