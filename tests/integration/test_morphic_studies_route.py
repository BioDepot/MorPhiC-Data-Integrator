"""
Verifies /api/morphic-studies only surfaces bulk RNA-seq studies that also
have a linked entry in perSampleMetadata.tsv, since selecting a study without
one would later fail at the metadata-fetch step on the MorPhiC Data screen.
"""
import pytest

import web.routes as routes

pytestmark = pytest.mark.integration


def _morphic_data(studies):
    return {"_embedded": {"studies": studies}}


def _bulk_rnaseq_study(title, erp=None, gse=None):
    accessions = [a for a in (erp, gse) if a]
    return {
        "content": {"study_title": title, "target_genes": "", "readout_assay": "RNA-seq"},
        "accessions": accessions,
    }


def test_only_studies_with_linked_metadata_entry_are_returned(client, monkeypatch):
    studies = [
        _bulk_rnaseq_study("Has ERP entry", erp="ERP1", gse="GSE1"),
        _bulk_rnaseq_study("No linked entry", erp="ERP404", gse="GSE404"),
        _bulk_rnaseq_study("Has GSE-only entry", gse="GSE2"),
    ]
    monkeypatch.setattr(routes.utils, "load_json_file", lambda name: _morphic_data(studies))
    monkeypatch.setattr(
        routes.utils, "get_available_morphic_study_ids", lambda: {"ERP1", "GSE1", "GSE2"}
    )
    # "Has GSE-only entry" has no ERP accession, so the route looks one up
    # via the SRA API -- stub that out so this test doesn't hit the network.
    monkeypatch.setattr(routes.sra_web_api, "get_erp_from_gse_id", lambda gse_id: "")

    response = client.get("/api/morphic-studies")

    assert response.status_code == 200
    titles = {s["study_title"] for s in response.get_json()}
    assert titles == {"Has ERP entry", "Has GSE-only entry"}


def test_shows_all_studies_unfiltered_if_metadata_file_unreadable(client, monkeypatch):
    studies = [_bulk_rnaseq_study("Some study", erp="ERP1", gse="GSE1")]
    monkeypatch.setattr(routes.utils, "load_json_file", lambda name: _morphic_data(studies))

    def _raise(*args, **kwargs):
        raise FileNotFoundError("perSampleMetadata.tsv")

    monkeypatch.setattr(routes.utils, "get_available_morphic_study_ids", _raise)

    response = client.get("/api/morphic-studies")

    assert response.status_code == 200
    titles = {s["study_title"] for s in response.get_json()}
    assert titles == {"Some study"}
