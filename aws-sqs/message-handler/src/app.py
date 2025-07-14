import json, time

def handler(event, context):
    # Loop through each record in the event
    for record in event.get('Records', []):
        # Extract the message body
        message_body = record.get('body')
        print(f"Processing message: {message_body}")
        
        # Perform your message processing logic here
        try:
            data = json.loads(message_body)
            # Example: Process the data
            print(f"Processed data: {data}")
        except json.JSONDecodeError:
            print("Failed to decode message body as JSON")
        
        # Add any additional processing logic as needed

    time.sleep(5)
    
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Messages processed successfully"})
    }
