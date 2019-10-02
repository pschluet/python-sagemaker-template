STACK_NAME=model-server-pipeline
DEPLOYMENT_BUCKET=cf-deploy-1eeb111769f855e024546b6f5d94be21

# Create Cloudformation deployment S3 bucket if it doesn't exist
if aws s3api head-bucket --bucket "$DEPLOYMENT_BUCKET" 2>/dev/null; then
    echo S3 bucket $DEPLOYMENT_BUCKET already exists. Not creating it.
else
    aws s3api create-bucket --bucket $DEPLOYMENT_BUCKET
    echo Created S3 bucket: $DEPLOYMENT_BUCKET.
fi

# Package and upload the lambdas and create the modified Cloudformation template
aws cloudformation package \
    --template-file model-server.yaml \
    --output-template-file model-server.packaged.yaml \
    --s3-bucket $DEPLOYMENT_BUCKET

# Deploy the modified Cloudformation template
aws cloudformation update-stack \
    --stack-name $STACK_NAME \
    --template-body file://model-server.packaged.yaml \
    --parameters file://model-server-parameters.json \
    --capabilities CAPABILITY_NAMED_IAM

aws cloudformation wait stack-update-complete --stack-name $STACK_NAME

rm model-server.packaged.yaml