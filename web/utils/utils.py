"""
Provides a collection of general purpsose utility functions for common operations such as string processing.
"""
import json
import os
import pandas as pd

def format_genes_from_str_to_list(input_genes: str) -> list:
    """
    Make a new list from string containing genes.

    Args:
        input_genes (str): A string containing genes, genes must be separated by white space
    
    Returns:
        list: a list of genes.
    """
    genes = input_genes.split()
    genes = [gene.strip() for gene in genes if gene.strip()]

    return genes
    
def save_json_file(data, file_name: str, indent=4):
    """
    Save Python Object as JSON file.

    Args:
        data (Any): Python object to save.
        file_name (str): Name of file, example: 'my_name.json'
    
    Returns:
        bool: True if file was saved, False otherwise.
    """
    try:
        with open(file_name, 'w') as f:
            json.dump(data, f, indent=indent)
        return True
    except IOError as e:
        print(f"Error saving JSON file: {e}")
        return False

def load_json_file(file_name: str):
    """
    Load JSON file and returns its content.

    Args:
        file_name (str): Name of file, example: 'my_name.json'
    
    Returns:
        dict, list, or None: The parsed JSON object, otherwise None when error occurs.
    """
    try:
        with open(file_name, 'r') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return None
    
def load_csv_file_as_df(file_name):
    """
    Load CSV file and return its content as pandas DataFrame.

    Args:
        file_name (str): Name of file, example: 'my_name.json'
    
    Returns:
        pd.DataFrame or None: Pandas DataFrame if successful, otherwise None.
    """
    try:
        df = pd.read_csv(file_name)
        return df
    except Exception as e:
        print(f"Error loading CSV file as pandas Dataframe: {e}")
        return None

def subset_counts_file(merged_counts_path, sample_ids, output_path):
    """
    Subset the columns of a merged gene counts TSV (genes as rows, samples as
    columns, first column is the gene name column) down to just the requested
    sample ids, and write the result out as a TSV.

    Fails fast (raises ValueError) if any requested sample id is not present
    among the columns of merged_counts_path, since that means the caller
    asked for a sample that doesn't have preprocessed counts available.

    Args:
        merged_counts_path (str): Path to the full merged counts TSV.
        sample_ids (list): Sample (column) ids to retain, e.g. ERR run accessions.
        output_path (str): Path to write the subset TSV to.

    Returns:
        None
    """
    with open(merged_counts_path, newline="") as fh:
        header = fh.readline().rstrip("\n").split("\t")

    header_set = set(header)
    missing_samples = [sample_id for sample_id in sample_ids if sample_id not in header_set]
    if missing_samples:
        raise ValueError(
            f"{merged_counts_path} has no column{'s' if len(missing_samples) != 1 else ''} for sample"
            f"{'s' if len(missing_samples) != 1 else ''}: {', '.join(missing_samples)}."
        )

    name_col = header[0]
    usecols = [name_col] + list(sample_ids)
    df = pd.read_csv(merged_counts_path, sep="\t", usecols=usecols)
    df = df[usecols]
    df.to_csv(output_path, sep="\t", index=False)

def merge_counts_tables(new_counts_path, merged_counts_path, morphic_sample_ids, output_path):
    """
    Merge a genesCounts.csv produced by the bulkrna_paired_unpaired.json
    alignment workflow with a subset of preprocessed MorPhiC samples pulled
    from mergedCounts.tsv, into a single counts table (same TSV shape: a
    "Name" gene-id column plus one column per sample) suitable for the
    PCA/DESeq2 container.

    Only genes present in both inputs are kept (inner join on "Name"), since
    DESeq2 requires a single consistent gene set across all samples.

    Args:
        new_counts_path (str): genesCounts.csv from the alignment workflow's
            output/Tables directory.
        merged_counts_path (str): path to mergedCounts.tsv.
        morphic_sample_ids (list): MorPhiC ERR ids to pull from merged_counts_path.
            May be empty/None if the user selected no preprocessed MorPhiC samples,
            in which case new_counts_path is used as-is.
        output_path (str): where to write the merged TSV.

    Returns:
        None
    """
    new_df = pd.read_csv(new_counts_path, sep="\t")

    if not morphic_sample_ids:
        new_df.to_csv(output_path, sep="\t", index=False)
        return

    morphic_subset_path = f"{output_path}.morphic_subset.tmp"
    try:
        subset_counts_file(merged_counts_path, morphic_sample_ids, morphic_subset_path)
        morphic_df = pd.read_csv(morphic_subset_path, sep="\t")
        morphic_df = morphic_df.rename(columns={morphic_df.columns[0]: new_df.columns[0]})
        merged_df = pd.merge(new_df, morphic_df, on=new_df.columns[0], how="inner")
        merged_df.to_csv(output_path, sep="\t", index=False)
    finally:
        if os.path.exists(morphic_subset_path):
            os.remove(morphic_subset_path)

def get_available_morphic_study_ids(file_name="perSampleMetadata.tsv"):
    """
    Return the set of ERP/GSE study ids that have at least one row in
    perSampleMetadata.tsv, i.e. studies with sample-level metadata actually
    available. Studies missing from this set would fail if selected on the
    MorPhiC Data screen, since get_morphic_metadata_for_gse_ids would have
    nothing to return for them.

    Args:
        file_name (str): Path to perSampleMetadata.tsv.

    Returns:
        set: erpAccession and gseAccession values present in the file.
    """
    per_sample_df = pd.read_csv(file_name)
    return set(per_sample_df['erpAccession'].dropna().unique()) | \
        set(per_sample_df['gseAccession'].dropna().unique())

def get_morphic_metadata_for_gse_ids(study_ids, file_name="perSampleMetadata.tsv"):
    """
    Look up per-sample metadata (cell line / knockout gene / time point) for a
    list of MorPhiC study ids directly from perSampleMetadata.tsv. No SRA/pysradb
    API calls are made — MorPhiC sample metadata is sourced entirely from this
    spreadsheet.

    The MorPhiC Data screen identifies studies by ERP accession (falling back to
    GEO/GSE accession only when no ERP accession is available), so study ids are
    matched against both the erpAccession and gseAccession columns.

    Fails fast (raises ValueError) if any requested study id has no matching rows
    in perSampleMetadata.tsv, since that means the spreadsheet is out of date
    and needs to be regenerated.

    Args:
        study_ids (list): ERP or GSE study ids to look up.
        file_name (str): Path to perSampleMetadata.tsv.

    Returns:
        pd.DataFrame: Rows with columns run_accession, study_accession, sampleName,
            cellLine, modelSystems, knockoutGene, genotypeStatus, timepoint for
            every sample belonging to the requested studies.
    """
    per_sample_df = pd.read_csv(file_name)

    studies_available = get_available_morphic_study_ids(file_name)
    missing_studies = [study_id for study_id in study_ids if study_id not in studies_available]
    if missing_studies:
        raise ValueError(
            f"perSampleMetadata.tsv has no entries for stud{'y' if len(missing_studies) == 1 else 'ies'}: "
            f"{', '.join(missing_studies)}. Regenerate {file_name} to include "
            "these studies before continuing."
        )

    matches = per_sample_df['erpAccession'].isin(study_ids) | per_sample_df['gseAccession'].isin(study_ids)
    subset = per_sample_df[matches].rename(columns={
        'errId': 'run_accession',
        'erpAccession': 'study_accession',
    })

    return subset[[
        'run_accession', 'study_accession', 'sampleName', 'cellLine',
        'modelSystems', 'knockoutGene', 'genotypeStatus', 'timepoint',
    ]]
