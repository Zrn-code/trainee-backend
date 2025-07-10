import time

def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "body": "Hello from Lambda!"
    }

def lambda_handler_long(event, context):
    time.sleep(5)  # Simulate long computation
    return {
        "statusCode": 200,
        "body": "Hello from Lambda after a long wait!"
    }
