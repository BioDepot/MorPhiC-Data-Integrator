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

# fetch metadata for given accession id
def get_metadata_for_gse_ids(accession_id_list: list, save_to_file: bool = True) -> list:
    """
        Get metadata with library stategies for corresponding ERP id's.

        Parameters:
            accession_id_list (list): A list of ERP id's as strings.
            save_to_file (bool): When True save results as file

        Returns:
            dict: A dictionary containing metadata request information:
                - ids_with_metadata (list): List of id's (str) with retrieved metadata
                - ids_with_not_metadata (list): List of ids (str) with no retrieved metadata
                - saved_file_name (str, optional): Name of saved file
            Otherwise None
    """
    if not accession_id_list:
        return None
    
    request_info = {"ids_with_metadata": [], "ids_with_no_metadata": []}
    metadata_collection = []

    db = SRAweb()
    for erp_id in accession_id_list:
        try:
            # srp_df = db.gse_to_srp(gse_id)
            # study_accession = srp_df['study_accession'].iloc[0]

            # fetch the metadata associated with ERP project ID
            metadata_df = db.sra_metadata(erp_id, detailed=True)
            # metadata_df.to_csv("{}.tsv".format(erp_id), sep="\t", index=False)

            # track metadata results
            col_names = ['run_accession', 'study_accession', 'derivedfrom', 'experiment_desc', 'library_layout', 'library_strategy']
            metadata_subset = metadata_df[metadata_df.columns.intersection(set(col_names))]
            metadata_collection.append(metadata_subset)

            request_info["ids_with_metadata"].append(erp_id)
        except Exception as e:
            error_message = f"Error: pysradb was unable to retrieve data for gse id {erp_id} \n {e}"
            print(error_message)
            request_info["ids_with_no_metadata"].append(erp_id)
            time.sleep(0.5)
        time.sleep(0.5)

    # save metadata collection to csv
    if metadata_collection and save_to_file:
        metadata_collection = pd.concat(metadata_collection, ignore_index=True)
        # metadata_collection.to_json('metadata.json')
        file_name = "metadata.csv"
        metadata_collection.to_csv(file_name, index=False)
        request_info["saved_file_name"] = file_name
    return request_info