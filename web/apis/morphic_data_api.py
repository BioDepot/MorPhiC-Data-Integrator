import requests

class MorphicAPI:
    """Handles communication with MorPhiC Public Release Studies API."""

    def __init__(self):
        self.base_url = 'https://api.ingest.dev.archive.morphic.bio'

    def get_data(self):
        """
        Get studies data from the MorPhiC Public Release data.

        Returns:
            dict: The API response as json if successful, otherwise None.
        """
        endpoint = "studies/search/findByReleaseStatus?releaseStatus=PUBLIC&page=0&size=20"
        url = f"{self.base_url}/{endpoint}"

        url = "https://api.ingest.dev.archive.morphic.bio/studies/search/findByReleaseStatus?releaseStatus=PUBLIC&page=0&size=20"
        try:
            response = requests.get(url)
            return response.json()
        except requests.RequestException as e:
            print(f"Error getting MorPhiC data: {e}")
            return None
