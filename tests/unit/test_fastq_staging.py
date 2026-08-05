import io
import os

import pytest
from werkzeug.datastructures import FileStorage

from web.utils import fastq_staging

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("filename", [
    "sample.fastq.gz",
    "sample.fq.gz",
    "SAMPLE.FASTQ.GZ",
    "sample.FQ.GZ",
])
def test_is_valid_fastq_upload_filename_accepts(filename):
    assert fastq_staging.is_valid_fastq_upload_filename(filename) is True


@pytest.mark.parametrize("filename", [
    "sample.fastq",
    "sample.fq",
    "sample.txt",
    "sample.fastq.gz.txt",
    "",
    None,
])
def test_is_valid_fastq_upload_filename_rejects(filename):
    assert fastq_staging.is_valid_fastq_upload_filename(filename) is False


def test_stage_uploaded_fastq_normalizes_fq_gz_to_fastq_gz(tmp_path):
    paired_dir = str(tmp_path / "paired")
    unpaired_dir = str(tmp_path / "unpaired")

    r1 = FileStorage(stream=io.BytesIO(b"gzipped-bytes"), filename="original_name.fq.gz")

    paths = fastq_staging.stage_uploaded_fastq("MYSAMPLE", "SINGLE", r1, None, paired_dir, unpaired_dir)

    assert paths == [os.path.join(unpaired_dir, "MYSAMPLE_R1.fastq.gz")]
    assert os.path.exists(paths[0])


def test_staged_fastq_paths_paired(tmp_path):
    paired_dir = str(tmp_path / "paired")
    unpaired_dir = str(tmp_path / "unpaired")

    target_dir, paths = fastq_staging.staged_fastq_paths("SAMPLE1", True, paired_dir, unpaired_dir)

    assert target_dir == paired_dir
    assert paths == [
        os.path.join(paired_dir, "SAMPLE1_R1.fastq.gz"),
        os.path.join(paired_dir, "SAMPLE1_R2.fastq.gz"),
    ]


def test_staged_fastq_paths_unpaired(tmp_path):
    paired_dir = str(tmp_path / "paired")
    unpaired_dir = str(tmp_path / "unpaired")

    target_dir, paths = fastq_staging.staged_fastq_paths("SAMPLE1", False, paired_dir, unpaired_dir)

    assert target_dir == unpaired_dir
    assert paths == [os.path.join(unpaired_dir, "SAMPLE1_R1.fastq.gz")]


def test_stage_uploaded_fastq_paired(tmp_path):
    paired_dir = str(tmp_path / "paired")
    unpaired_dir = str(tmp_path / "unpaired")

    r1 = FileStorage(stream=io.BytesIO(b"r1-bytes"), filename="whatever_r1.fastq.gz")
    r2 = FileStorage(stream=io.BytesIO(b"r2-bytes"), filename="whatever_r2.fastq.gz")

    paths = fastq_staging.stage_uploaded_fastq("MYSAMPLE", "PAIRED", r1, r2, paired_dir, unpaired_dir)

    assert paths == [
        os.path.join(paired_dir, "MYSAMPLE_R1.fastq.gz"),
        os.path.join(paired_dir, "MYSAMPLE_R2.fastq.gz"),
    ]
    assert open(paths[0], "rb").read() == b"r1-bytes"
    assert open(paths[1], "rb").read() == b"r2-bytes"
    assert not os.path.exists(os.path.join(unpaired_dir, "MYSAMPLE_R1.fastq.gz"))


def test_stage_uploaded_fastq_single(tmp_path):
    paired_dir = str(tmp_path / "paired")
    unpaired_dir = str(tmp_path / "unpaired")

    r1 = FileStorage(stream=io.BytesIO(b"only-read"), filename="whatever.fastq.gz")

    paths = fastq_staging.stage_uploaded_fastq("MYSAMPLE", "SINGLE", r1, None, paired_dir, unpaired_dir)

    assert paths == [os.path.join(unpaired_dir, "MYSAMPLE_R1.fastq.gz")]
    assert open(paths[0], "rb").read() == b"only-read"
    assert not os.path.isdir(paired_dir)


def test_download_srr_fastq_paired(tmp_path, mocker):
    paired_dir = str(tmp_path / "paired")
    unpaired_dir = str(tmp_path / "unpaired")

    mocker.patch(
        "web.utils.fastq_staging.sra_web_api.get_ena_fastq_urls",
        return_value=(True, ["http://example.com/SRR1_1.fastq.gz", "http://example.com/SRR1_2.fastq.gz"]),
    )

    downloaded_bodies = {
        "http://example.com/SRR1_1.fastq.gz": b"read-one",
        "http://example.com/SRR1_2.fastq.gz": b"read-two",
    }

    def fake_get(url, stream=True, timeout=60):
        response = mocker.MagicMock()
        response.raise_for_status = mocker.MagicMock()
        response.iter_content = lambda chunk_size=None: iter([downloaded_bodies[url]])
        response.__enter__ = mocker.MagicMock(return_value=response)
        response.__exit__ = mocker.MagicMock(return_value=False)
        return response

    mocker.patch("web.utils.fastq_staging.requests.get", side_effect=fake_get)

    paths = fastq_staging.download_srr_fastq("SRR1", paired_dir, unpaired_dir)

    assert paths == [
        os.path.join(paired_dir, "SRR1_R1.fastq.gz"),
        os.path.join(paired_dir, "SRR1_R2.fastq.gz"),
    ]
    assert open(paths[0], "rb").read() == b"read-one"
    assert open(paths[1], "rb").read() == b"read-two"


def test_download_srr_fastq_single(tmp_path, mocker):
    paired_dir = str(tmp_path / "paired")
    unpaired_dir = str(tmp_path / "unpaired")

    mocker.patch(
        "web.utils.fastq_staging.sra_web_api.get_ena_fastq_urls",
        return_value=(False, ["http://example.com/SRR2.fastq.gz"]),
    )

    def fake_get(url, stream=True, timeout=60):
        response = mocker.MagicMock()
        response.raise_for_status = mocker.MagicMock()
        response.iter_content = lambda chunk_size=None: iter([b"single-end-bytes"])
        response.__enter__ = mocker.MagicMock(return_value=response)
        response.__exit__ = mocker.MagicMock(return_value=False)
        return response

    mocker.patch("web.utils.fastq_staging.requests.get", side_effect=fake_get)

    paths = fastq_staging.download_srr_fastq("SRR2", paired_dir, unpaired_dir)

    assert paths == [os.path.join(unpaired_dir, "SRR2_R1.fastq.gz")]
    assert open(paths[0], "rb").read() == b"single-end-bytes"


def _fake_get_serving(mocker, bodies_by_url):
    def fake_get(url, stream=True, timeout=60):
        response = mocker.MagicMock()
        response.raise_for_status = mocker.MagicMock()
        response.iter_content = lambda chunk_size=None: iter([bodies_by_url[url]])
        response.__enter__ = mocker.MagicMock(return_value=response)
        response.__exit__ = mocker.MagicMock(return_value=False)
        return response
    return fake_get


def test_download_srr_fastq_uses_cache_on_second_call(tmp_path, mocker):
    cache_dir = str(tmp_path / "cache")
    first_paired_dir = str(tmp_path / "run1" / "paired")
    first_unpaired_dir = str(tmp_path / "run1" / "unpaired")
    second_paired_dir = str(tmp_path / "run2" / "paired")
    second_unpaired_dir = str(tmp_path / "run2" / "unpaired")

    mocker.patch(
        "web.utils.fastq_staging.sra_web_api.get_ena_fastq_urls",
        return_value=(True, ["http://example.com/SRR1_1.fastq.gz", "http://example.com/SRR1_2.fastq.gz"]),
    )
    fake_get = mocker.patch(
        "web.utils.fastq_staging.requests.get",
        side_effect=_fake_get_serving(mocker, {
            "http://example.com/SRR1_1.fastq.gz": b"read-one",
            "http://example.com/SRR1_2.fastq.gz": b"read-two",
        }),
    )

    first_paths = fastq_staging.download_srr_fastq(
        "SRR1", first_paired_dir, first_unpaired_dir, cache_dir=cache_dir
    )
    assert fake_get.call_count == 2
    assert open(first_paths[0], "rb").read() == b"read-one"
    assert open(first_paths[1], "rb").read() == b"read-two"

    # Second run (different destination dirs) should reuse the cached files
    # instead of hitting the network again.
    second_paths = fastq_staging.download_srr_fastq(
        "SRR1", second_paired_dir, second_unpaired_dir, cache_dir=cache_dir
    )
    assert fake_get.call_count == 2  # unchanged: no new network calls
    assert second_paths != first_paths
    assert open(second_paths[0], "rb").read() == b"read-one"
    assert open(second_paths[1], "rb").read() == b"read-two"


def test_download_srr_fastq_propagates_lookup_error(tmp_path, mocker):
    paired_dir = str(tmp_path / "paired")
    unpaired_dir = str(tmp_path / "unpaired")

    mocker.patch(
        "web.utils.fastq_staging.sra_web_api.get_ena_fastq_urls",
        side_effect=ValueError("No ENA FASTQ files found for accession SRR404"),
    )

    with pytest.raises(ValueError, match="SRR404"):
        fastq_staging.download_srr_fastq("SRR404", paired_dir, unpaired_dir)
