import requests

def lambda_handler(event, context):
    r = requests.get("https://api.github.com")
    return {
        "statusCode": 200,
        "body": f"GitHub status: {r.status_code}"
    }