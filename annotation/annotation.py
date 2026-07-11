import boto3
import pymysql
import os
from urllib.parse import unquote_plus
import google.generativeai as genai  # Gemini API for image captioning
import base64  # Encoding image data for API processing

DB_HOST = os.environ.get("DB_HOST", "")
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "image_caption_db")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel(model_name=GEMINI_MODEL)

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
        print(f"Gemini caption generation failed with model {GEMINI_MODEL}: {e}")
        raise

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
    try:
        caption = generate_image_caption(image_bytes)
        print(f"Generated caption for {image_key}: {caption[:200]}")
    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Caption generation failed for {image_key}: {str(e)}",
        }

    # Insert caption into RDS
    connection = None
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            connect_timeout=5,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE captions SET caption = %s WHERE image_key = %s",
                (caption, image_key),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO captions (image_key, caption) VALUES (%s, %s)",
                    (image_key, caption),
                )
                print(f"Inserted caption row for {image_key}")
            else:
                print(f"Updated caption row for {image_key}")
        connection.commit()
    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Database update failed for {image_key}: {str(e)}",
        }
    finally:
        if connection:
            connection.close()

    return {
        "statusCode": 200,
        "body": f"Annotation for {image_key} stored successfully."
    }
