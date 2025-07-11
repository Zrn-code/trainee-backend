import threading
import requests
import time

def fetch_data():
    
    url = "http://localhost:3000/api/long-hello"  # Local testing URL
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"Error fetching data: {e}")

def main():
    threads = []
    total_requests = 100
    requests_per_second = 5
    interval = 1  # 1 second

    for i in range(total_requests):
        thread = threading.Thread(target=fetch_data)
        threads.append(thread)
        thread.start()

        
        if (i + 1) % requests_per_second == 0:
            time.sleep(interval)

    for thread in threads:  # Wait for all threads to complete
        thread.join()

if __name__ == "__main__":
    main()
