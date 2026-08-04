"""
Runs the real patrickmckeever/rnotebook:0.3 container (Rscript /app/pca.R) end
to end against a small, real subset of mergedCounts.tsv, the same way
web/routes.py's /run-bwb "no uploads / no manual SRR ids" branch does.

Requires:
    - a working `docker` CLI with access to the internet (pulls the image,
      and the R script itself calls out to biomaRt/Ensembl), and
    - ./mergedCounts.tsv present at the repo root.

Run explicitly with: PYTHONPATH=. pytest -m e2e tests/e2e/test_pca_container.py
"""
import os
import shutil
import subprocess

import pytest

from web.utils import utils

pytestmark = pytest.mark.e2e

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MERGED_COUNTS_PATH = os.path.join(REPO_ROOT, "mergedCounts.tsv")

# Real MorPhiC ERR ids known to be columns in mergedCounts.tsv.
CONTROL_SAMPLES = ["ERR13982538", "ERR13982572"]
TREATED_SAMPLES = ["ERR13982588", "ERR13982580"]
SAMPLE_IDS = CONTROL_SAMPLES + TREATED_SAMPLES

requires_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker CLI not available"
)
requires_merged_counts = pytest.mark.skipif(
    not os.path.exists(MERGED_COUNTS_PATH), reason="mergedCounts.tsv not present at repo root"
)


def build_metadata_json(output_path):
    utils.save_json_file({
        "groups": [
            {
                "name": "control",
                "samples": [
                    {"srr_id": srr_id, "layout": "PAIRED", "preprocessed": True}
                    for srr_id in CONTROL_SAMPLES
                ],
            },
            {
                "name": "treated",
                "samples": [
                    {"srr_id": srr_id, "layout": "PAIRED", "preprocessed": True}
                    for srr_id in TREATED_SAMPLES
                ],
            },
        ]
    }, output_path)


@requires_docker
@requires_merged_counts
def test_pca_container_produces_plots(tmp_path):
    counts_dir = tmp_path / "processing" / "Tables"
    counts_dir.mkdir(parents=True)

    # This is exactly the function/call web/routes.py's /run-bwb "no uploads /
    # no manual SRR ids" branch uses to build genesCounts.csv, over the full
    # gene set, so the container sees the same shape of input it would in
    # production.
    genes_counts_path = counts_dir / "genesCounts.csv"
    utils.subset_counts_file(MERGED_COUNTS_PATH, SAMPLE_IDS, str(genes_counts_path))

    metadata_path = tmp_path / "metadata.json"
    build_metadata_json(str(metadata_path))

    counts_dir_str = str(counts_dir)
    metadata_path_str = str(metadata_path)

    cmd = (
        f"docker run --rm "
        f"-v {counts_dir_str}:{counts_dir_str} "
        f"-v {metadata_path_str}:{metadata_path_str} "
        f"-e counts_dir={counts_dir_str} "
        f"-e metadata_json={metadata_path_str} "
        f"patrickmckeever/rnotebook:0.3 Rscript /app/pca.R"
    )

    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=1800
    )

    assert result.returncode == 0, (
        f"pca.R container exited with {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )

    for filename in ("volcano_plot.png", "pca_plot.png", "heatmap.png"):
        output_file = counts_dir / filename
        assert output_file.exists(), f"expected {filename} in {counts_dir_str}"
        assert output_file.stat().st_size > 0
