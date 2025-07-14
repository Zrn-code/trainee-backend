import json
import boto3
import os
from PIL import Image
import io
from urllib.parse import unquote_plus

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    Process SQS messages containing S3 events for image conversion
    """
    
    source_bucket = os.environ['SOURCE_BUCKET']
    destination_bucket = os.environ['DESTINATION_BUCKET']
    
    for record in event['Records']:
        try:
            # Parse the SQS message body (EventBridge event)
            message_body = json.loads(record['body'])
            
            # Extract S3 object information
            bucket_name = message_body['detail']['bucket']['name']
            object_key = unquote_plus(message_body['detail']['object']['key'])
            
            print(f"Processing image: {object_key} from bucket: {bucket_name}")
            
            # Download the image from S3
            response = s3_client.get_object(Bucket=source_bucket, Key=object_key)
            image_content = response['Body'].read()
            
            # Convert image to different formats
            convert_image(image_content, object_key, destination_bucket)
            
            print(f"Successfully processed image: {object_key}")
            
        except Exception as e:
            print(f"Error processing record: {str(e)}")
            raise e
    
    return {
        'statusCode': 200,
        'body': json.dumps('Image processing completed successfully')
    }

def convert_image(image_content, original_key, destination_bucket):
    """
    Convert image to different formats and sizes
    """
    
    # Open the image
    image = Image.open(io.BytesIO(image_content))
    
    # Define conversion formats and sizes
    conversions = [
        {'format': 'JPEG', 'quality': 85, 'suffix': '_compressed.jpg'},
        {'format': 'WEBP', 'quality': 80, 'suffix': '_optimized.webp'},
        {'size': (800, 600), 'format': 'JPEG', 'quality': 90, 'suffix': '_medium.jpg'},
        {'size': (200, 150), 'format': 'JPEG', 'quality': 85, 'suffix': '_thumbnail.jpg'}
    ]
    
    # Get the base name without extension
    base_name = os.path.splitext(original_key)[0]
    
    for conversion in conversions:
        try:
            # Create a copy of the image
            converted_image = image.copy()
            
            # Resize if size is specified
            if 'size' in conversion:
                converted_image.thumbnail(conversion['size'], Image.Resampling.LANCZOS)
            
            # Convert to RGB if saving as JPEG
            if conversion['format'] == 'JPEG' and converted_image.mode in ('RGBA', 'P'):
                converted_image = converted_image.convert('RGB')
            
            # Save to BytesIO
            output_buffer = io.BytesIO()
            save_kwargs = {'format': conversion['format']}
            
            if 'quality' in conversion:
                save_kwargs['quality'] = conversion['quality']
                save_kwargs['optimize'] = True
            
            converted_image.save(output_buffer, **save_kwargs)
            output_buffer.seek(0)
            
            # Generate the new key
            new_key = f"converted/{base_name}{conversion['suffix']}"
            
            # Upload to destination bucket
            s3_client.put_object(
                Bucket=destination_bucket,
                Key=new_key,
                Body=output_buffer.getvalue(),
                ContentType=f"image/{conversion['format'].lower()}"
            )
            
            print(f"Converted and uploaded: {new_key}")
            
        except Exception as e:
            print(f"Error converting image with format {conversion}: {str(e)}")
            continue
