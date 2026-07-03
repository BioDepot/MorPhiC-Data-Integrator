"""
Provides a collection of general purpsose utility functions for common operations such as string processing.
"""
import json
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
