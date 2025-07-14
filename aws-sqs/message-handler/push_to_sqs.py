import boto3
import json

# Initialize the SQS client with a specific region
sqs = boto3.client('sqs', region_name='us-east-1')  # Replace 'us-east-1' with your region

# Replace with your SQS queue URL
QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/516224964203/MyQueue"

def send_message(message_body):
    try:
        # Send a message to the SQS queue
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message_body)
        )
        print(f"Message sent! Message ID: {response['MessageId']}")
    except Exception as e:
        print(f"Failed to send message: {e}")

if __name__ == "__main__":
    # Send 60 messages to the SQS queue
    for i in range(1, 61):
        message = {
            "id": i,
            "name": f"Test Message {i}",
            "description": f"This is test message number {i} for SQS."
        }
        send_message(message)
