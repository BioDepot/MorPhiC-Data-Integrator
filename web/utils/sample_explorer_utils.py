"""
Provides a collection of helpful functions for common operations needed to process Sample Explorer API data.
"""
from typing import Dict, List

def get_unique_gse_ids(data: Dict[str, Dict[str, List[Dict[str, str]]]]) -> List[str]:
    """
    Extract unique items from the 'data' section of a given dictionary.

    Args:
        data (dict): A dictionary containing data about gse studies (expansion, samples, seed) and their gse id's.
    
    Returns:
        list: a list of unique items across all studies.
    """
    unique_gse_ids = set()

    data = data.get('data', {})
    for study in data.get('expansion_studies', []):
        gse_id = study.get('gse_id')
        if gse_id:
            unique_gse_ids.add(gse_id)
    for study in data.get('samples', []):
        gse_id = study.get('series_id')
        if gse_id:
            unique_gse_ids.add(gse_id)
    for study in data.get('seed_studies', []):
        gse_id = study.get('gse_id')
        if gse_id:
            unique_gse_ids.add(gse_id)

    return list(unique_gse_ids)

def split_gse_ids(studies: list, gse_id_label: str):
    """
    Splits comma-separated gse ids strings that are part of study into its own study.

    Args:
        studies (list): List of studies as dictionaries containing gse id's, some gse id's have more than one id that are comma separated.

    Returns:
        list: A list of individual, unique gse ids.
    """
    updated_studies = []
    for study in studies:
        gse_ids = [gse_id.strip() for gse_id in study[gse_id_label].split(',')]
        if len(gse_ids) > 1:
            for gse_id in gse_ids:
                modified_study = study.copy()
                modified_study[gse_id_label] = gse_id
                updated_studies.append(modified_study)
        else:
            updated_studies.append(study)
    
    return updated_studies

def remove_duplicate_gse_ids(studies: list, gse_id_label: str):
    """
    Removes duplicate gse id's.

    Args:
        studies (list): List of Studies as dictionaries containing gse id's
        gse_id_label (str): Label of a key in studies dictionary

    Returns:
        list: A list studies that does not have duplicate gse id's.
    """
    unique_gse_ids = set()
    updated_studies = []
    for study in studies:
        gse_id = study[gse_id_label]
        if gse_id not in unique_gse_ids:
            updated_studies.append(study.copy())
        unique_gse_ids.add(gse_id)
    return updated_studies

def reshape_data(data: dict):
    """
    Cleans nested dictonary studies data by processing lists within its study.
    
    For each list, it splits string that are comma-separated gse ids and removes duplicates.

    Args:
        data (dict): A dictionary containing a 'data' key, which has a dictionary of studies.
    
    Returns:
        dict: A dictionary with cleaned data.
    """
    if not data:
        return data

    updated_expansion_studies = split_gse_ids(data['data']['expansion_studies'], 'gse_id')
    updated_expansion_studies = remove_duplicate_gse_ids(updated_expansion_studies, 'gse_id')
    data['data']['expansion_studies'] = updated_expansion_studies

    updated_samples = split_gse_ids(data['data']['samples'], 'series_id')
    data['data']['samples'] = updated_samples

    updated_seed_studies = split_gse_ids(data['data']['seed_studies'], 'gse_id')
    updated_seed_studies = remove_duplicate_gse_ids(updated_seed_studies, 'gse_id')
    data['data']['seed_studies'] = updated_seed_studies

    return data

def add_sample_type_to_studies_data(sample_data: dict, studies_data: dict):
    """
    Add sample type, Bulk or Single-cell, from samples data to studies data.

    Args:
        sample_data (dict): A dictionary containing a gse id as a key, and a sample type a string value.
        studies_data (dict): A dictionary containing a 'data' key, which has a dictionary of studies.
    
    Returns:
        dict: A dictionary with cleaned data.
    """
    data = studies_data.get('data', {})

    for study in data.get('expansion_studies', []):
        gse_id = study.get('gse_id')
        sample_type = sample_data.get(gse_id, '')
        if gse_id:
            study['sample_type'] = sample_type

    for study in data.get('samples', []):
        gse_id = study.get('series_id')
        sample_type = sample_data.get(gse_id, '')
        if gse_id:
            study['sample_type'] = sample_type

    for study in data.get('seed_studies', []):
        gse_id = study.get('gse_id')
        sample_type = sample_data.get(gse_id, '')
        if gse_id:
            study['sample_type'] = sample_type

    return studies_data

