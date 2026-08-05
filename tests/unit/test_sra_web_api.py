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

def test_get_ena_fastq_urls_paired(mocker):
    mock_sra_web = mocker.patch('web.apis.sra_web_api.SRAweb')
    mock_instance = mock_sra_web.return_value
    mock_instance.fetch_ena_fastq.return_value = pd.DataFrame({
        "run_accession": ["ERR1"],
        "ena_fastq_http_1": ["http://example.com/ERR1_1.fastq.gz"],
        "ena_fastq_http_2": ["http://example.com/ERR1_2.fastq.gz"],
    })

    is_paired, urls = sra_web_api.get_ena_fastq_urls("ERR1")
    assert is_paired is True
    assert urls == ["http://example.com/ERR1_1.fastq.gz", "http://example.com/ERR1_2.fastq.gz"]

def test_get_ena_fastq_urls_single(mocker):
    mock_sra_web = mocker.patch('web.apis.sra_web_api.SRAweb')
    mock_instance = mock_sra_web.return_value
    mock_instance.fetch_ena_fastq.return_value = pd.DataFrame({
        "run_accession": ["SRR1"],
        "ena_fastq_http": ["http://example.com/SRR1.fastq.gz"],
        "ena_fastq_ftp": ["ftp://example.com/SRR1.fastq.gz"],
    })

    is_paired, urls = sra_web_api.get_ena_fastq_urls("SRR1")
    assert is_paired is False
    assert urls == ["http://example.com/SRR1.fastq.gz"]

def test_get_ena_fastq_urls_missing_raises(mocker):
    mock_sra_web = mocker.patch('web.apis.sra_web_api.SRAweb')
    mock_instance = mock_sra_web.return_value
    mock_instance.fetch_ena_fastq.return_value = pd.DataFrame({
        "run_accession": [],
        "ena_fastq_http": [],
    })

    with pytest.raises(ValueError, match="SRR404"):
        sra_web_api.get_ena_fastq_urls("SRR404")