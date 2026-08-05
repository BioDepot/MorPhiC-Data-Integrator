import pytest
from web.utils import utils, sample_explorer_utils

pytestmark = pytest.mark.unit

# UTILS

# @pytest.mark.unit
def test_format_genes_from_str_to_list():
    genes_from_text_area = "MMP8\nLTF\nCAMP\nHP\nDCLK2\nGOLGA8R\nKIR3DL2\nPTPRN2-AS1\nSERPINB9\nB3GAT1"
    result = ["MMP8", "LTF", "CAMP", "HP", "DCLK2", "GOLGA8R", "KIR3DL2", "PTPRN2-AS1", "SERPINB9", "B3GAT1"]
    assert utils.format_genes_from_str_to_list(genes_from_text_area) == result

def test_subset_counts_file_success(tmp_path):
    merged = tmp_path / "mergedCounts.tsv"
    merged.write_text(
        "Name\tERR1\tERR2\tERR3\n"
        "ENSG1\t10\t20\t30\n"
        "ENSG2\t1\t2\t3\n"
    )
    out = tmp_path / "genesCounts.csv"

    utils.subset_counts_file(str(merged), ["ERR2", "ERR1"], str(out))

    assert out.read_text() == (
        "Name\tERR2\tERR1\n"
        "ENSG1\t20\t10\n"
        "ENSG2\t2\t1\n"
    )

def test_subset_counts_file_missing_sample_raises(tmp_path):
    merged = tmp_path / "mergedCounts.tsv"
    merged.write_text(
        "Name\tERR1\tERR2\n"
        "ENSG1\t10\t20\n"
    )
    out = tmp_path / "genesCounts.csv"

    with pytest.raises(ValueError, match="ERR9"):
        utils.subset_counts_file(str(merged), ["ERR1", "ERR9"], str(out))

def test_merge_counts_tables_with_morphic_samples(tmp_path):
    new_counts = tmp_path / "genesCounts.csv"
    new_counts.write_text(
        "Name\tSAMPLE1\tSAMPLE2\n"
        "ENSG1\t10\t20\n"
        "ENSG2\t1\t2\n"
        "ENSG3\t5\t6\n"
    )
    merged_counts = tmp_path / "mergedCounts.tsv"
    merged_counts.write_text(
        "Name\tERR1\tERR2\n"
        "ENSG1\t100\t200\n"
        "ENSG2\t11\t22\n"
        "ENSG4\t99\t88\n"
    )
    out = tmp_path / "merged.tsv"

    utils.merge_counts_tables(str(new_counts), str(merged_counts), ["ERR1", "ERR2"], str(out))

    result = out.read_text()
    assert result == (
        "Name\tSAMPLE1\tSAMPLE2\tERR1\tERR2\n"
        "ENSG1\t10\t20\t100\t200\n"
        "ENSG2\t1\t2\t11\t22\n"
    )
    # No leftover temp file
    assert not (tmp_path / "merged.tsv.morphic_subset.tmp").exists()

def test_merge_counts_tables_no_morphic_samples_copies_new_counts(tmp_path):
    new_counts = tmp_path / "genesCounts.csv"
    new_counts.write_text(
        "Name\tSAMPLE1\n"
        "ENSG1\t10\n"
    )
    merged_counts = tmp_path / "mergedCounts.tsv"
    merged_counts.write_text(
        "Name\tERR1\n"
        "ENSG1\t100\n"
    )
    out = tmp_path / "merged.tsv"

    utils.merge_counts_tables(str(new_counts), str(merged_counts), [], str(out))

    assert out.read_text() == "Name\tSAMPLE1\n" "ENSG1\t10\n"

def test_merge_counts_tables_missing_morphic_sample_raises(tmp_path):
    new_counts = tmp_path / "genesCounts.csv"
    new_counts.write_text("Name\tSAMPLE1\nENSG1\t10\n")
    merged_counts = tmp_path / "mergedCounts.tsv"
    merged_counts.write_text("Name\tERR1\nENSG1\t100\n")
    out = tmp_path / "merged.tsv"

    with pytest.raises(ValueError, match="ERR9"):
        utils.merge_counts_tables(str(new_counts), str(merged_counts), ["ERR9"], str(out))

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