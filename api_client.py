import requests
from config import REPORT_KILL_URL, REPORT_DEATH_URL


class APIClient:
    def __init__(self, key_store):
        self.api_key = key_store

    def post_kill_event(self, kill_result):
        data = kill_result["data"]
        headers = {"Authorization": f"Bearer {self.api_key['value']}"}
        requests.post(REPORT_KILL_URL, headers=headers, json=data, timeout=5)

    def post_death_event(self, payload):
        headers = {"Authorization": f"Bearer {self.api_key['value']}"}
        requests.post(REPORT_DEATH_URL, headers=headers, json=payload, timeout=5)
