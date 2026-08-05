"""
Stages FASTQ inputs (user uploads and downloaded SRR/ERR accessions) into the
paired/unpaired directory layout bulkrna_paired_unpaired.json expects:

    {paired_fastq_dir}/{SAMPLE_ID}_R1.fastq.gz
    {paired_fastq_dir}/{SAMPLE_ID}_R2.fastq.gz
    {unpaired_fastq_dir}/{SAMPLE_ID}_R1.fastq.gz
"""
import os
import shutil

import requests

from web.apis import sra_web_api

# Uploaded FASTQ files must already be gzip-compressed -- an uncompressed
# .fastq upload would still get saved under a .fastq.gz name (stage_uploaded_fastq
# always normalizes the basename), but its contents wouldn't actually be gzip,
# which breaks the alignment workflow's readFilesCommand/gunzip handling.
ALLOWED_UPLOAD_SUFFIXES = (".fastq.gz", ".fq.gz")


def is_valid_fastq_upload_filename(filename):
    """
    True if filename ends with an accepted compressed FASTQ extension
    (.fastq.gz or .fq.gz), case-insensitive.

    Parameters:
        filename (str): the uploaded file's original filename.

    Returns:
        bool
    """
    if not filename:
        return False
    return filename.lower().endswith(ALLOWED_UPLOAD_SUFFIXES)


def staged_fastq_paths(sample_id, is_paired, paired_dir, unpaired_dir):
    """
    Resolve the destination directory and file path(s) for a sample.

    Parameters:
        sample_id (str): sample name / run accession used as the file basename.
        is_paired (bool): whether the sample has R1 and R2 reads.
        paired_dir (str): destination directory for paired-end samples.
        unpaired_dir (str): destination directory for single-end samples.

    Returns:
        tuple(str, list): (target_dir, paths) — paths has 2 entries (R1, R2)
        if is_paired, otherwise 1 entry.
    """
    target_dir = paired_dir if is_paired else unpaired_dir
    paths = [os.path.join(target_dir, f"{sample_id}_R1.fastq.gz")]
    if is_paired:
        paths.append(os.path.join(target_dir, f"{sample_id}_R2.fastq.gz"))
    return target_dir, paths


def stage_uploaded_fastq(sample_id, layout, r1_file, r2_file, paired_dir, unpaired_dir):
    """
    Save an uploaded FASTQ file (or pair) for one sample using the
    SAMPLE_ID_R{1,2}.fastq.gz naming bulkrna_paired_unpaired.json expects.

    Parameters:
        sample_id (str): user-supplied sample name (not the uploaded file's own name).
        layout (str): "PAIRED" or "SINGLE".
        r1_file: werkzeug FileStorage for read 1.
        r2_file: werkzeug FileStorage for read 2, required if layout == "PAIRED".
        paired_dir (str): destination directory for paired-end samples.
        unpaired_dir (str): destination directory for single-end samples.

    Returns:
        list: paths the file(s) were saved to.
    """
    is_paired = layout == "PAIRED"
    target_dir, paths = staged_fastq_paths(sample_id, is_paired, paired_dir, unpaired_dir)
    os.makedirs(target_dir, exist_ok=True)

    r1_file.save(paths[0])
    if is_paired:
        r2_file.save(paths[1])

    return paths


def download_srr_fastq(srr_id, paired_dir, unpaired_dir, cache_dir=None):
    """
    Download an SRA/ENA run accession's FASTQ file(s) directly from ENA and
    stage them into paired_dir or unpaired_dir depending on library layout.

    Parameters:
        srr_id (str): SRA/ENA run accession, e.g. "SRR12345678".
        paired_dir (str): destination directory for paired-end runs.
        unpaired_dir (str): destination directory for single-end runs.
        cache_dir (str): optional shared directory to cache downloaded FASTQ
            files in, keyed by accession. If a previous run already downloaded
            this accession's file(s) into cache_dir, they're copied from there
            instead of being re-downloaded from ENA.

    Returns:
        list: paths the file(s) were saved to.
    """
    is_paired, urls = sra_web_api.get_ena_fastq_urls(srr_id)
    target_dir, paths = staged_fastq_paths(srr_id, is_paired, paired_dir, unpaired_dir)
    os.makedirs(target_dir, exist_ok=True)

    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_paths = [os.path.join(cache_dir, os.path.basename(path)) for path in paths]

        if not all(os.path.exists(cache_path) for cache_path in cache_paths):
            for url, cache_path in zip(urls, cache_paths):
                _download_file(url, cache_path)

        for cache_path, dest_path in zip(cache_paths, paths):
            shutil.copyfile(cache_path, dest_path)

        return paths

    for url, path in zip(urls, paths):
        _download_file(url, path)

    return paths


def _download_file(url, dest_path):
    tmp_path = f"{dest_path}.part"
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(tmp_path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    os.replace(tmp_path, dest_path)
