import requests

class SampleExplorerAPI:
    """Handles communication with SampleExplorer API."""

    def __init__(self):
        self.base_url = 'http://127.0.0.1:5001'

    def make_query(
            self, 
            user_uuid: str, 
            text_query_used: bool, 
            query: str, 
            gene_set_used: bool, 
            gene_set: list, 
            search: str, 
            expand: str
        ):
        """
        Make a query with specified details.

        Parameters:
            user_uuid (str): The ID of the query.
            text_query_used (bool): Indication if query text is to be used.
            text_query (str): A text based query or search.
            gene_set_used (bool): Indication if list of genes is to be used.
            gene_set (list): A list comprised of genes example, ['gene1', 'gene2', … ], there should be at least 5
            search (str): Expansion strategy, should only be semantic or transcriptome
            expand (str): Expansion strategy, should only be semantic or transcriptome

        Returns:
            dict: The API response if successful, or dictionary with 'error' as key and error info as value.
        """
        endpoint = "query_rag"
        url = f"{self.base_url}/{endpoint}"
        payload = {
            'uuid': user_uuid,
            'text_query_used': text_query_used,
            'text_query': query,
            'gene_set_used': gene_set_used,
            'gene_set': gene_set,
            'search': search,
            'expand': expand
        }

        try:
            response = requests.post(url, json=payload)
            print('response from server:', response.text)
            if response.status_code == 400 or response.status_code == 200:
                return response.json()
            response.raise_for_status()

            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"Error making a query to /{endpoint}: Connection error")
            return {"error": "Connection error"}
        except requests.exceptions.RequestException as e:
            print(f"Error making a query to /{endpoint}: {e}")
            return {"error": str(e)}
        
    def get_queue_position(self, user_uuid):
        """
        Fetch queue position of a query.

        Parameters:
            user_uuid (str): The ID of the query whose queue position is being retrived.

        Returns:
            dict: The API response if successful, or None if failed.
        """
        endpoint = "queue_position"
        url = f"{self.base_url}/{endpoint}"
        payload = {
            'uuid': user_uuid
        }
        
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            # print('get queue position, response from server:', response.text)
            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"Error getting queue position from /{endpoint}: Connection error")
            return None
        except requests.RequestException as e:
            print(f"Error getting queue position from /{endpoint}: {e}")
            return None

    def get_data_output(self, user_uuid, lines):
        """
        Fetch data of the query results.

        Parameters:
            user_uuid (str): The ID of the query.
            lines (str): The amount of maximum rows requested in the data.

        Returns:
            dict: The API response if successful, or None if failed.
        """
        endpoint = "data_output"
        url = f"{self.base_url}/{endpoint}"
        payload = {
            'uuid': user_uuid,
            'amount_of_lines': int(lines)
        }
        
        try:
            response = requests.post(url, json=payload)
            # print('data_output, response from server:', str(response.text)[:100])
            response.raise_for_status()

            return response.json()
        except requests.exceptions.ConnectionError:
            print(f"Error getting data output from /{endpoint}: Connection error")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error getting data output from /{endpoint}: {e}")
            return None
        
    def get_download_file(self, user_uuid, lines):
        """
        Fetch zip file of the data from a query.

        Parameters:
            user_uuid (str): The ID of the query.
            lines (str): The amount of maximum rows requested in the data.

        Returns:
            dict: The API response if successful with 'content' key containing the raw contents of the file ZIP file (bytes), or None if failed.
        """
        endpoint = "file_download"
        url = f"{self.base_url}/{endpoint}"
        payload = {
            'uuid': user_uuid,
            'amount_of_lines': lines
        }

        try:
            response_file = requests.post(url, json=payload)
            response_file.raise_for_status()

            return response_file
        except requests.exceptions.ConnectionError:
            print(f"Error getting download file fron /{endpoint}: Connection error")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error getting download file fron /{endpoint}: {e}")
            return None
