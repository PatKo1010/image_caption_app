# Image Captioning App

This project is a Flask image-captioning application deployed on AWS. Users upload an image through the web app, the app stores the image in S3, generates a caption with the Gemini API, saves image metadata and captions in MySQL on RDS, and displays uploaded images in a gallery.

The production deployment uses CloudFormation for the AWS resources:

- VPC with public and private subnets
- Internet Gateway and NAT Gateway
- S3 bucket for uploaded images
- Private RDS MySQL database
- EC2 Auto Scaling Group
- Application Load Balancer
- Optional Lambda functions for thumbnail generation

## Application Structure

```text
app.py                         Flask application
config.py                      Local runtime configuration, ignored by git
templates/                     Flask HTML templates
create_architecture.yaml       VPC, subnets, S3, RDS, NAT, security groups
create_ec2_asg.yaml            ALB, launch template, target group, ASG
create_lambda_function.yaml    Lambda functions for thumbnail/annotation flow
create-database.sh             MySQL database/table initialization script
ASG_DEPLOYMENT.md              Detailed ASG deployment notes
LAMBDA_DEPLOYMENT.md           Detailed Lambda deployment notes
```

## Runtime Configuration

Create `config.py` on the EC2 AMI or instance. Do not commit real secrets.

```python
GOOGLE_API_KEY = "your-gemini-api-key"
GEMINI_MODEL = "gemini-3.5-flash"

S3_BUCKET = "your-image-bucket"
S3_REGION = "us-east-1"

DB_HOST = "your-rds-endpoint"
DB_NAME = "image_caption_db"
DB_USER = "admin"
DB_PASSWORD = "your-db-password"

APP_LOG_FILE = "logs/app.log"
```

## Prerequisites

Install and configure the AWS CLI:

```bash
aws configure --profile my-aws
aws sts get-caller-identity --profile my-aws
```

You need IAM permissions for CloudFormation, EC2, ELBv2, Auto Scaling, RDS, S3, IAM PassRole for the EC2 instance profile, and Lambda if deploying the Lambda stack.

The current ASG template uses:

```text
Key pair: imageCaptioningKey
Instance profile: Ec2UploadS3
AMI ID: ami-0580f448a4ccdfcfb
Instance type: t3.micro
```

Update those values in `create_ec2_asg.yaml` if your account uses different names or AMIs.

## 1. Deploy Base Architecture

The architecture stack creates the network, S3 bucket, RDS database, NAT gateway, and security groups.

If you already have an Internet Gateway attached to the VPC:

```bash
aws cloudformation deploy \
  --stack-name image-caption-architecture \
  --template-file create_architecture.yaml \
  --parameter-overrides \
    DBUsername=admin \
    DBPassword='your-db-password' \
    InternetGatewayId=igw-xxxxxxxxxxxxxxxxx \
    CreateInternetGateway=false \
  --profile my-aws
```

If you want CloudFormation to create the Internet Gateway:

```bash
aws cloudformation deploy \
  --stack-name image-caption-architecture \
  --template-file create_architecture.yaml \
  --parameter-overrides \
    DBUsername=admin \
    DBPassword='your-db-password' \
    CreateInternetGateway=true \
  --profile my-aws
```

Get the architecture outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name image-caption-architecture \
  --profile my-aws \
  --query 'Stacks[0].Outputs' \
  --output table
```

Record these values:

- `VPCId`
- `PublicSubnetId`
- `PublicSubnet2Id`
- `RDSEndpoint`
- `RDSSecurityGroupId`
- `BucketName`

## 2. Initialize the Database

SSH into an EC2 instance that can reach the private RDS database and run:

```bash
cd ~/image_caption_app
chmod +x create-database.sh
./create-database.sh
```

The script creates:

```sql
image_caption_db
captions
```

## 3. Build an AMI for the ASG

Prepare a working EC2 instance with this project at:

```text
/home/ec2-user/image_caption_app
```

Make sure it includes:

```text
app.py
config.py
templates/
```

Create an AMI from that instance:

```bash
aws ec2 create-image \
  --instance-id i-xxxxxxxxxxxxxxxxx \
  --name image-caption-app-ami \
  --description "AMI for image caption app" \
  --profile my-aws
```

When the AMI becomes `available`, update `ImageId` in `create_ec2_asg.yaml`.

## 4. Deploy ASG and ALB

Find the EC2 instance security group ID if it is not in the architecture outputs:

```bash
aws ec2 describe-security-groups \
  --profile my-aws \
  --filters Name=tag:Name,Values=EC2InstanceSecurityGroup Name=vpc-id,Values=<vpc-id> \
  --query 'SecurityGroups[0].GroupId' \
  --output text
```

Deploy the ASG stack:

```bash
aws cloudformation deploy \
  --stack-name image-caption-asg \
  --template-file create_ec2_asg.yaml \
  --parameter-overrides \
    VPCId=<vpc-id> \
    PublicSubnetId=<public-subnet-1> \
    PublicSubnetId2=<public-subnet-2> \
    InstanceSecurityGroupId=<ec2-instance-security-group-id> \
    RdsEc2SecurityGroupId=<rds-security-group-id> \
  --profile my-aws
```

Get the ALB URL:

```bash
aws cloudformation describe-stacks \
  --stack-name image-caption-asg \
  --profile my-aws \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerURL`].OutputValue' \
  --output text
```

Open:

```text
http://<load-balancer-url>
```

## 5. Optional Lambda Deployment

The current web app generates captions inside `app.py`. The Lambda stack is optional and can be used for thumbnail generation or older async annotation workflows.

Package and upload Lambda code:

```bash
cd annotation/lambda_package
zip -qr ../../annotation.zip .

cd ../../thumbnail/lambda_package
zip -qr ../../thumbnail.zip .

cd ../..
aws s3 cp annotation.zip s3://<lambda-code-bucket>/annotation.zip --profile my-aws
aws s3 cp thumbnail.zip s3://<lambda-code-bucket>/thumbnail.zip --profile my-aws
```

Deploy Lambda stack:

```bash
aws cloudformation deploy \
  --stack-name image-caption-lambda \
  --template-file create_lambda_function.yaml \
  --parameter-overrides \
    LambdaExecutionRoleArn=arn:aws:iam::<account-id>:role/ImageCaptionLambdaExecutionRole \
    CodeBucket=<lambda-code-bucket> \
    ImageBucketName=<image-bucket> \
    AnnotationSubnetIds="<private-subnet-1>,<private-subnet-2>" \
    AnnotationSecurityGroupId=<lambda-security-group-id> \
    DBHost=<rds-endpoint> \
    DBName=image_caption_db \
    DBUser=admin \
    DBPassword='your-db-password' \
    GoogleApiKey='your-gemini-api-key' \
    GeminiModel=gemini-3.5-flash \
    AnnotationZipKey=annotation.zip \
    ThumbnailZipKey=thumbnail.zip \
  --profile my-aws
```

See `LAMBDA_DEPLOYMENT.md` for more Lambda details.

## Health Checks

Check stack status:

```bash
aws cloudformation describe-stacks \
  --stack-name image-caption-asg \
  --profile my-aws \
  --query 'Stacks[0].StackStatus' \
  --output text
```

Check ASG instances:

```bash
aws autoscaling describe-auto-scaling-groups \
  --profile my-aws \
  --query 'AutoScalingGroups[?contains(AutoScalingGroupName, `image-caption-asg`)].Instances[*].[InstanceId,LifecycleState,HealthStatus]' \
  --output table
```

Check target health:

```bash
aws cloudformation describe-stack-resources \
  --stack-name image-caption-asg \
  --logical-resource-id ALBTargetGroup \
  --profile my-aws \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text
```

Then:

```bash
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --profile my-aws \
  --output table
```

## Troubleshooting

SSH to an ASG instance:

```bash
ssh -i imageCaptioningKey.pem ec2-user@<instance-public-ip>
```

Check app logs:

```bash
cd ~/image_caption_app
tail -n 100 logs/gunicorn.log
tail -n 100 logs/app.log
```

Check cloud-init user data logs:

```bash
sudo tail -n 100 /var/log/cloud-init-output.log
```

Check that Gunicorn is running:

```bash
ps aux | grep gunicorn
curl http://localhost:5000/gallery
```

Common issues:

- `iam:PassRole` missing for the EC2 instance profile role.
- AMI does not contain `/home/ec2-user/image_caption_app`.
- `config.py` is missing or has wrong DB/S3/Gemini values.
- ALB target group health check `/gallery` fails because the app cannot connect to RDS.
- EC2 security group does not allow port `5000`.
- RDS security group does not allow MySQL `3306` from the EC2 security group.
