import json

import pytest

from web.routes import write_metadata_json

pytestmark = pytest.mark.unit

# These samples/srr_groups/srr_entries shapes mirror exactly what the
# frontend (uploaded on the MorPhiC Data page, assigned to groups on the
# Metadata page) sends to /run-bwb as `samples[i][...]`, `srr_metadata_json`
# and `srr_entries[i][...]` respectively. No docker/subprocess involved.


def test_write_metadata_json_combines_uploads_assignments_and_manual_srr_ids(tmp_path):
    samples = [
        {"name": "uploaded_sample_1", "group": "Control", "layout": "SINGLE"},
    ]
    srr_groups = [
        {"name": "Control", "samples": ["SRR000001"]},
        {"name": "Treatment", "samples": ["SRR000002", "SRR000003"]},
    ]
    srr_entries = [
        {"id": "SRR999999", "group": "Treatment"},
    ]

    output_path = tmp_path / "metadata.json"
    write_metadata_json(samples=samples, srr_groups=srr_groups, srr_entries=srr_entries, output_path=output_path)

    with open(output_path) as fh:
        metadata = json.load(fh)

    groups_by_name = {g["name"]: g["samples"] for g in metadata["groups"]}

    assert groups_by_name["Control"] == [
        {"srr_id": "uploaded_sample_1", "layout": "SINGLE", "preprocessed": False},
        {"srr_id": "SRR000001", "layout": "PAIRED", "preprocessed": True},
    ]
    assert groups_by_name["Treatment"] == [
        {"srr_id": "SRR000002", "layout": "PAIRED", "preprocessed": True},
        {"srr_id": "SRR000003", "layout": "PAIRED", "preprocessed": True},
        {"srr_id": "SRR999999", "layout": "PAIRED", "preprocessed": False},
    ]


def test_write_metadata_json_handles_no_uploads_or_manual_srr_ids(tmp_path):
    srr_groups = [
        {"name": "Control", "samples": ["SRR000001"]},
        {"name": "Treatment", "samples": []},
    ]

    output_path = tmp_path / "metadata.json"
    write_metadata_json(samples=[], srr_groups=srr_groups, srr_entries=[], output_path=output_path)

    with open(output_path) as fh:
        metadata = json.load(fh)

    groups_by_name = {g["name"]: g["samples"] for g in metadata["groups"]}
    assert groups_by_name["Control"] == [
        {"srr_id": "SRR000001", "layout": "PAIRED", "preprocessed": True},
    ]
    # A group with no assigned samples never gets an entry (write_metadata_json
    # only creates group keys when it iterates a non-empty samples list).
    assert "Treatment" not in groups_by_name
