import boto3
import os
from PIL import Image
import io

s3 = boto3.client('s3')

def lambda_handler(event, context):
    # Get bucket and key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    if key.startswith('thumbnails/'):
        return {"status": "Skipped thumbnail generation for thumbnail image"}

    # Download the image from S3
    image_object = s3.get_object(Bucket=bucket, Key=key)
    image_content = image_object['Body'].read()
    
    # Create thumbnail
    image = Image.open(io.BytesIO(image_content))
    image.thumbnail((128, 128))  # size can be changed

    # Save thumbnail to buffer
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG')
    buffer.seek(0)

    # Upload thumbnail to thumbnails/ directory
    thumb_key = f"thumbnails/{os.path.basename(key)}"
    s3.put_object(Bucket=bucket, Key=thumb_key, Body=buffer, ContentType='image/jpeg')

    return {"status": "Thumbnail generated", "thumbnail_key": thumb_key}
