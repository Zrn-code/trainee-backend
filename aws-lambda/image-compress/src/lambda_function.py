import json
import boto3
import os
from botocore.exceptions import ClientError
from PIL import Image
import io

# Initialize S3 client
s3_client = boto3.client('s3')
SOURCE_BUCKET = os.environ['SOURCE_BUCKET']
COMPRESSED_BUCKET = os.environ['COMPRESSED_BUCKET']

def compress_image(image_bytes, quality=85, max_width=1920, max_height=1080):
    """
    Compress and resize image
    """
    try:
        # Open image from bytes
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary (for JPEG compatibility)
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        
        # Resize image if it's too large
        if image.width > max_width or image.height > max_height:
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # Compress image
        output_buffer = io.BytesIO()
        image.save(output_buffer, format='JPEG', quality=quality, optimize=True)
        output_buffer.seek(0)
        
        return output_buffer.getvalue()
    
    except Exception as e:
        print(f'Error compressing image: {str(e)}')
        raise e

def lambda_handler(event, context):
    """
    Lambda handler that processes S3 image upload events, compresses images, and uploads to compressed bucket
    """
    print(f'Event: {json.dumps(event)}')
    
    # Handle warm-up events
    if 'source' in event and event['source'] == 'aws.events' and event.get('detail-type') == 'Lambda Warm-up':
        print('Warm-up event received - keeping Lambda function warm')
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Lambda function warmed up successfully'
            })
        }
    
    try:
        # EventBridge event structure is different from S3 Records
        if 'source' in event and event['source'] == 'aws.s3':
            # This is an EventBridge event
            bucket = event['detail']['bucket']['name']
            key = event['detail']['object']['key']
            
            print(f'Image uploaded: {key} in bucket {bucket}')
            print(f'Event name: {event["detail-type"]}')
            
            # Try to get basic object info, but don't fail if we can't access it
            try:
                response = s3_client.head_object(Bucket=bucket, Key=key)
                file_size = response['ContentLength']
                content_type = response.get('ContentType', 'unknown')
                
                print(f'File size: {file_size} bytes')
                print(f'Content type: {content_type}')
                
                # Download the original image
                print('Downloading original image...')
                obj = s3_client.get_object(Bucket=bucket, Key=key)
                image_bytes = obj['Body'].read()
                
                # Compress the image
                print('Compressing image...')
                compressed_image = compress_image(image_bytes)
                
                # Generate compressed file name
                file_name, file_ext = os.path.splitext(key)
                compressed_key = f"compressed/{file_name}.jpg"
                
                # Upload compressed image to compressed bucket
                print(f'Uploading compressed image to {COMPRESSED_BUCKET}/{compressed_key}')
                s3_client.put_object(
                    Bucket=COMPRESSED_BUCKET,
                    Key=compressed_key,
                    Body=compressed_image,
                    ContentType='image/jpeg'
                )
                
                compressed_size = len(compressed_image)
                compression_ratio = (1 - compressed_size / file_size) * 100
                
                print(f'Compression completed:')
                print(f'Original size: {file_size} bytes')
                print(f'Compressed size: {compressed_size} bytes')
                print(f'Compression ratio: {compression_ratio:.1f}%')
                
            except ClientError as s3_error:
                error_code = s3_error.response['Error']['Code']
                print(f'Warning: Could not access S3 object metadata. Error: {error_code} - {s3_error}')
                print('This might be due to missing S3 permissions. Event processing will continue.')
            except Exception as s3_error:
                print(f'Warning: Unexpected error accessing S3 object: {str(s3_error)}')
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'S3 event processed successfully'
            })
        }
        
    except Exception as error:
        print(f'Error processing S3 event: {str(error)}')
        raise error
