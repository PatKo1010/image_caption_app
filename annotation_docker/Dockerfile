FROM public.ecr.aws/lambda/python:3.9

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt -t .

# Copy function code
COPY annotation.py .

# Set the CMD to your handler
CMD ["annotation.lambda_handler"]