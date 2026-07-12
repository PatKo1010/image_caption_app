# ASG and ALB Deployment

This deploys `create_ec2_asg.yaml`, which creates:

- EC2 Launch Template
- Internet-facing Application Load Balancer
- ALB security group allowing inbound HTTP on port `80`
- Target Group on port `5000`
- HTTP listener on port `80`
- Auto Scaling Group across two public subnets

## Prerequisites

Deploy `create_architecture.yaml` first. The current architecture stack outputs are:

```text
VPCId:            vpc-00dfa1cc366005c09
PublicSubnetId:   subnet-0ebb4202dda6b1b56
PublicSubnet2Id:  subnet-070cd3d1d9c878aa5
PrivateSubnetId:  subnet-000cd72e77b5b9205
PrivateSubnet2Id: subnet-0fb113b11913d255e
```

The AMI used in `create_ec2_asg.yaml` must already contain the application files at:

```text
/home/ec2-user/image_caption_app
```

Expected files include:

```text
app.py
config.py
templates/
```

The deploying IAM user must be allowed to pass the EC2 instance profile role used by the launch template. This template uses:

```text
Ec2UploadS3
```

If deployment fails with `You are not authorized to use launch template`, add `iam:PassRole` permission for the role behind that instance profile.

## Get Existing Security Group IDs

Get the EC2 instance security group from the architecture stack:

```bash
aws cloudformation describe-stacks \
  --stack-name image-caption-architecture \
  --profile my-aws \
  --query 'Stacks[0].Outputs[?OutputKey==`RDSSecurityGroupId` || OutputKey==`VPCId`].[OutputKey,OutputValue]' \
  --output table
```

If you need the EC2 instance security group ID and it is not output by the stack, find it by name:

```bash
aws ec2 describe-security-groups \
  --profile my-aws \
  --filters Name=group-name,Values=EC2InstanceSecurityGroup Name=vpc-id,Values=vpc-00dfa1cc366005c09 \
  --query 'SecurityGroups[0].GroupId' \
  --output text
```

## Validate Template

```bash
aws cloudformation validate-template \
  --template-body file://create_ec2_asg.yaml \
  --profile my-aws
```

## Deploy Stack

Replace the two security group placeholders before running. The ALB security group is created by this stack.

```bash
aws cloudformation deploy \
  --stack-name image-caption-asg \
  --template-file create_ec2_asg.yaml \
  --parameter-overrides \
    VPCId=vpc-00dfa1cc366005c09 \
    PublicSubnetId=subnet-0ebb4202dda6b1b56 \
    PublicSubnetId2=subnet-070cd3d1d9c878aa5 \
    InstanceSecurityGroupId=<ec2-instance-security-group-id> \
    RdsEc2SecurityGroupId=<rds-security-group-id> \
  --profile my-aws
```

## Get Load Balancer URL

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

## Check ASG and Target Health

Find the target group ARN:

```bash
aws cloudformation describe-stack-resources \
  --stack-name image-caption-asg \
  --logical-resource-id ALBTargetGroup \
  --profile my-aws \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text
```

Then check target health:

```bash
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --profile my-aws \
  --output table
```

## Troubleshooting

SSH to one ASG instance and check the app logs:

```bash
ssh -i imageCaptioningKey.pem ec2-user@<instance-public-ip>
cd ~/image_caption_app
tail -n 100 logs/gunicorn.log
tail -n 100 logs/app.log
```

Check that Gunicorn is listening on port `5000`:

```bash
ps aux | grep gunicorn
curl http://localhost:5000/gallery
```

If target health fails, check:

- The AMI contains `/home/ec2-user/image_caption_app/app.py`.
- `config.py` exists on the AMI and has the DB, S3, and Gemini settings.
- The EC2 security group allows inbound `5000` from the ALB security group.
- The RDS security group allows inbound `3306` from the EC2 instance security group.
- The app can reach Gemini over the internet.
