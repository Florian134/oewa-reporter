#!/usr/bin/env python3
"""Quick test to check API field names"""
import os
import requests
from datetime import date, timedelta

INFONLINE_API_KEY = os.environ.get("INFONLINE_API_KEY", "")

def test_api():
    test_date = date.today() - timedelta(days=7)
    
    for metric in ["pageimpressions", "visits", "uniqueclients"]:
        print(f"\n{'='*50}")
        print(f"Testing: {metric}")
        print(f"{'='*50}")
        
        url = f"https://reportingapi.infonline.de/api/v1/{metric}"
        params = {
            "site": "at_w_atvol",
            "date": test_date.isoformat(),
            "aggregation": "DAY"
        }
        headers = {
            "authorization": INFONLINE_API_KEY,
            "Accept": "application/json"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=30)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {data.keys()}")
            if "data" in data and "iom" in data["data"]:
                iom = data["data"]["iom"]
                if iom:
                    print(f"IOM entry keys: {iom[0].keys()}")
                    print(f"IOM entry: {iom[0]}")

if __name__ == "__main__":
    test_api()

