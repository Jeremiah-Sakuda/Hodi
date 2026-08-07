import requests
import sys

URL = "https://hodi-evidence-endpoint-406699565497.us-central1.run.app/api/v1/debug/compromised_agent_read"

def run_test():
    print("Testing valid properly scoped read...")
    resp0 = requests.post(URL, json={"attack_type": "valid_read"})
    print(resp0.json())
    assert resp0.json()["status"] == "SUCCESS", "Gateway failed to allow properly scoped read!"

    print("\nTesting unfiltered read...")
    resp1 = requests.post(URL, json={"attack_type": "unfiltered"})
    print(resp1.json())
    assert resp1.json()["status"] == "DENIED", "Gateway failed to block unfiltered read!"

    print("\nTesting cross_counterparty read...")
    resp2 = requests.post(URL, json={"attack_type": "cross_counterparty"})
    print(resp2.json())
    assert resp2.json()["status"] == "DENIED", "Gateway failed to block cross-counterparty read!"

    print("\nAll boundary tests PASSED successfully against live service.")

if __name__ == "__main__":
    run_test()
