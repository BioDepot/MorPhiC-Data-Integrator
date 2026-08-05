"""
Merges a real (fixture) genesCounts.csv, shaped like what
bulkrna_paired_unpaired.json's gatherCounts step produces, with a subset of
real MorPhiC ERR samples pulled from mergedCounts.tsv -- the same merge
web/routes.py's /run-bwb runs before invoking the PCA container when the user
combines uploaded/SRR samples with preprocessed MorPhiC samples.
"""
import os

import pandas as pd
import pytest

from web.utils import utils

pytestmark = pytest.mark.integration

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MERGED_COUNTS_PATH = os.path.join(REPO_ROOT, "mergedCounts.tsv")
WORKFLOW_COUNTS_FIXTURE = os.path.join(REPO_ROOT, "tests", "genesCounts.csv")

# Real MorPhiC ERR ids known to be columns in mergedCounts.tsv.
MORPHIC_SAMPLE_IDS = ["ERR13982538", "ERR13982572"]

requires_merged_counts = pytest.mark.skipif(
    not os.path.exists(MERGED_COUNTS_PATH), reason="mergedCounts.tsv not present at repo root"
)
requires_fixture = pytest.mark.skipif(
    not os.path.exists(WORKFLOW_COUNTS_FIXTURE), reason="tests/genesCounts.csv fixture not present"
)


@requires_merged_counts
@requires_fixture
def test_merge_counts_tables_with_real_fixture(tmp_path):
    output_path = tmp_path / "merged.tsv"

    utils.merge_counts_tables(
        WORKFLOW_COUNTS_FIXTURE, MERGED_COUNTS_PATH, MORPHIC_SAMPLE_IDS, str(output_path)
    )

    workflow_df = pd.read_csv(WORKFLOW_COUNTS_FIXTURE, sep="\t")
    merged_df = pd.read_csv(output_path, sep="\t")

    assert merged_df.columns[0] == "Name"
    # Every workflow sample column and every requested MorPhiC sample column
    # made it into the merged table.
    for col in workflow_df.columns[1:]:
        assert col in merged_df.columns
    for sample_id in MORPHIC_SAMPLE_IDS:
        assert sample_id in merged_df.columns

    # Inner join on gene id: never more rows than the smaller input, and
    # since both files share the same Ensembl gene set, effectively the same
    # gene count.
    assert 0 < len(merged_df) <= len(workflow_df)

    # Values for a shared gene/sample pair are carried through unchanged.
    sample_gene = workflow_df["Name"].iloc[0]
    assert sample_gene in set(merged_df["Name"])
    workflow_col = workflow_df.columns[1]
    expected = workflow_df.loc[workflow_df["Name"] == sample_gene, workflow_col].iloc[0]
    actual = merged_df.loc[merged_df["Name"] == sample_gene, workflow_col].iloc[0]
    assert expected == actual


@requires_merged_counts
@requires_fixture
def test_merge_counts_tables_missing_morphic_sample_raises(tmp_path):
    output_path = tmp_path / "merged.tsv"

    with pytest.raises(ValueError, match="NOT_A_REAL_SAMPLE"):
        utils.merge_counts_tables(
            WORKFLOW_COUNTS_FIXTURE, MERGED_COUNTS_PATH, ["NOT_A_REAL_SAMPLE"], str(output_path)
        )
