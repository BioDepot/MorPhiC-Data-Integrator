"""
Provides functions that help with retreving metadata using pysradb library.
"""

from pysradb import SRAweb
import pandas as pd
import time

# fetch_gse_library_strategy
def get_library_strategy_for_gse_ids(gse_list: list) -> dict:
    """
        Get metadata with library stategies for corresponding gse id's.

        Parameters:
            gse_list (list): A list of gse id's as strings.

        Returns:
            dict: Metadata containing library stratgies
    """
    # {'gse_id': 'strategy'}
    strategies = {}

    db = SRAweb()
    for gse_id in gse_list:
        try:
            srp_df = db.gse_to_srp(gse_id)
            study_accession = srp_df['study_accession'].iloc[0]
            metadata = db.sra_metadata(study_accession, detailed=False)

            contains_bulk = metadata['library_strategy'].str.contains('RNA-Seq').any()
            if contains_bulk:
                strategies[gse_id] = 'Bulk'
            else:
                strategies[gse_id] = 'Single-cell'
        except Exception as e:
            strategies[gse_id] = ''
            error_message = f"Error: pysradb was unable to retrieve data for gse id {gse_id} \n {e}"
            print(error_message)
            time.sleep(0.5)
        time.sleep(0.5)
    
    return strategies

# fetch_gse_metadata
def get_metadata_for_gse_ids(gse_list: list, save_to_file: bool = True) -> list:
    """
        Get metadata with library stategies for corresponding gse id's.

        Parameters:
            gse_list (list): A list of gse id's as strings.
            save_to_file (bool): When True save results as file

        Returns:
            list: List of metadata, metadata are pandas DataFrame
    """
    metadata_collection = []

    db = SRAweb()
    for gse_id in gse_list:
        try:
            srp_df = db.gse_to_srp(gse_id)
            study_accession = srp_df['study_accession'].iloc[0]
            metadata = db.sra_metadata(study_accession, detailed=True)

            # track metadata results
            metadata_subset = metadata[['run_accession', 'experiment_desc', 'source_name', 'library_layout']]
            metadata_collection.append(metadata_subset)
        except Exception as e:
            error_message = f"Error: pysradb was unable to retrieve data for gse id {gse_id} \n {e}"
            print(error_message)
            time.sleep(0.5)
        time.sleep(0.5)

    # save metadata collection to csv
    if metadata_collection and save_to_file:
        metadata_collection = pd.concat(metadata_collection, ignore_index=True)
        # metadata_collection.to_json('metadata.json')
        metadata_collection.to_csv("metadata.csv", index=False)
    return metadata_collection