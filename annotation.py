import json
import boto3
import pymysql
import os
from urllib.parse import unquote_plus
import google.generativeai as genai  # Gemini API for image captioning
import base64  # Encoding image data for API processing

# === HARDCODED DB CREDENTIALS ===
DB_HOST = "database-1.ccgo53b5lmnh.us-east-1.rds.amazonaws.com"
DB_USER = "admin"
DB_PASSWORD = "P19951010"
DB_NAME = "image_caption_db"

# Choose a Gemini model for generating captions
# Configure Gemini API, REPLACE with your Gemini API key
GOOGLE_API_KEY = "AIzaSyBuzPXvNYY4L6qBVGe-wbPYZfchCYkveSI"
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel(model_name="gemini-2.0-pro-exp-02-05")

# Simulated Gemini caption generator (replace with actual API call)
def generate_image_caption(image_data):
    """
    Generate a caption for an uploaded image using the Gemini API.

    :param image_data: Raw binary image data
    :return: Generated caption or error message
    """
    try:
        encoded_image = base64.b64encode(image_data).decode("utf-8")
        response = model.generate_content(
            [
                {"mime_type": "image/jpeg", "data": encoded_image},
                "Caption this image.",
            ]
        )
        return response.text if response.text else "No caption generated."
    except Exception as e:
        return f"Error: {str(e)}"

def lambda_handler(event, context):
    # Extract bucket name and object key from the event
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    image_key = unquote_plus(event['Records'][0]['s3']['object']['key'])

    if image_key.startswith("thumbnails/"):
        return {"statusCode": 200, "body": "Skipped thumbnail image."}

    # Download image from S3
    s3 = boto3.client('s3')
    response = s3.get_object(Bucket=bucket_name, Key=image_key)
    image_bytes = response['Body'].read()

    # Generate caption
    caption = generate_image_caption(image_bytes)

    # Insert caption into RDS
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        with connection.cursor() as cursor:
            sql = "UPDATE captions SET caption = %s WHERE image_key = %s"
            cursor.execute(sql, (caption, image_key))
        connection.commit()
    finally:
        connection.close()

    return {
        "statusCode": 200,
        "body": f"Annotation for {image_key} stored successfully."
    }

