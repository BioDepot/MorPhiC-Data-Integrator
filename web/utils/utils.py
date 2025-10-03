"""
Provides a collection of general purpsose utility functions for common operations such as string processing.
"""

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