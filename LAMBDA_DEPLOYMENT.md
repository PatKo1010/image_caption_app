# Lambda Deployment Notes

This project uses two AWS Lambda functions:

- `ThumbnailLambdaFunction`: creates a thumbnail after an image is uploaded to S3.
- `AnnotationLambdaFunction`: generates an image caption and updates the RDS MySQL row.

## Package Layout

The deployable Lambda packages live under:

```text
annotation/lambda_package/
thumbnail/lambda_package/
```

Each package directory should contain the handler file and its dependencies:

```text
annotation/lambda_package/
  annotation.py
  pymysql/
  google/
  ...

thumbnail/lambda_package/
  thumbnail.py
  PIL/
  pillow.libs/
  ...
```

Because the handler files are at the package root, `create_lambda_function.yaml` should use:

```yaml
Handler: annotation.lambda_handler
Handler: thumbnail.lambda_handler
```

## Build Zip Files

Run from the project root:

```bash
cd annotation/lambda_package
zip -r ../../annotation.zip .
cd ../..

cd thumbnail/lambda_package
zip -r ../../thumbnail.zip .
cd ../..
```

## Upload Lambda Code

Replace `YOUR_CODE_BUCKET` with the S3 bucket used for Lambda zip files:

```bash
aws s3 cp annotation.zip s3://YOUR_CODE_BUCKET/annotation.zip
aws s3 cp thumbnail.zip s3://YOUR_CODE_BUCKET/thumbnail.zip
```

## Create Lambda Execution Role

Create the trust policy:

```bash
cat > lambda-trust-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
```

Create the role:

```bash
aws iam create-role \
  --role-name ImageCaptionLambdaExecutionRole \
  --assume-role-policy-document file://lambda-trust-policy.json
```

Attach basic CloudWatch logging permission:

```bash
aws iam attach-role-policy \
  --role-name ImageCaptionLambdaExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

If the Lambda functions need to access private RDS inside a VPC, also attach:

```bash
aws iam attach-role-policy \
  --role-name ImageCaptionLambdaExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole
```

This policy is required when `AnnotationLambdaFunction` uses `VpcConfig`, because Lambda must create and manage ENIs in the VPC.

Create a project policy. Replace `YOUR_IMAGE_BUCKET` and `YOUR_ACCOUNT_ID`:

```bash
cat > lambda-project-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::YOUR_IMAGE_BUCKET/*"
    },
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:function:AnnotationLambdaFunction"
    }
  ]
}
EOF
```

Attach the project policy:

```bash
aws iam put-role-policy \
  --role-name ImageCaptionLambdaExecutionRole \
  --policy-name ImageCaptionLambdaProjectPolicy \
  --policy-document file://lambda-project-policy.json
```

Get the role ARN:

```bash
aws iam get-role \
  --role-name ImageCaptionLambdaExecutionRole \
  --query "Role.Arn" \
  --output text
```

## Deploy CloudFormation Stack

Replace `YOUR_ACCOUNT_ID`, `YOUR_CODE_BUCKET`, `YOUR_IMAGE_BUCKET`, private subnet IDs, security group ID, database values, and the role name if needed:

```bash
aws cloudformation deploy \
  --stack-name image-caption-lambda \
  --template-file create_lambda_function.yaml \
  --parameter-overrides \
    LambdaExecutionRoleArn=arn:aws:iam::YOUR_ACCOUNT_ID:role/ImageCaptionLambdaExecutionRole \
    CodeBucket=YOUR_CODE_BUCKET \
    ImageBucketName=YOUR_IMAGE_BUCKET \
    AnnotationSubnetIds="subnet-private1,subnet-private2" \
    AnnotationSecurityGroupId=sg-lambda \
    DBHost=your-rds-endpoint \
    DBName=image_caption_db \
    DBUser=admin \
    DBPassword='your-db-password' \
    GoogleApiKey='your-gemini-api-key' \
    GeminiModel=gemini-3.5-flash \
    AnnotationZipKey=annotation.zip \
    ThumbnailZipKey=thumbnail.zip
```

For private RDS plus Gemini access, the VPC must also have:

```text
private subnet route table -> 0.0.0.0/0 -> NAT Gateway
NAT Gateway -> public subnet
public subnet route table -> 0.0.0.0/0 -> Internet Gateway
RDS security group allows inbound 3306 from the Lambda security group
```

Check stack outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name image-caption-lambda \
  --query "Stacks[0].Outputs"
```

## Configure S3 Trigger

The CloudFormation template gives S3 permission to invoke the Lambdas, but it does not configure the S3 event notification.

Configure it manually:

```text
S3 -> your image bucket -> Properties -> Event notifications
```

Create an event notification:

```text
Event type: All object create events
Destination: Lambda function
Lambda: ThumbnailLambdaFunction
```

With the current design:

```text
S3 upload -> ThumbnailLambdaFunction -> AnnotationLambdaFunction
```

## Notes

- `boto3` does not need to be packaged because it is included in the Lambda runtime.
- The package dependencies should be built for the Lambda runtime OS and Python version.
- The current CloudFormation runtime is `python3.9`, so the package was built with Python 3.9 Linux-compatible wheels.
- `annotation/lambda_package` is large because `google-generativeai` pulls in many dependencies.
