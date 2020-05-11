#!/bin/bash

# Set environment variables
source set_env.sh

develop_branch_name='develop'
master_branch_name='master'

if [ ${GIT_BRANCH} = ${master_branch_name} ]; then
    environment_name=prod
else
    environment_name=dev
fi

# ------------- Create or Update AWS Cloudformation Stack -------------
# Only update Cloudformation stack if the git branch is master or develop
if [ ${GIT_BRANCH} = ${develop_branch_name} ] || [ ${GIT_BRANCH} = ${master_branch_name} ]; then
    if [ ${GIT_BRANCH} = ${master_branch_name} ]; then
        deploy_bucket_name=demo-master-deploy
    else
        deploy_bucket_name=demo-dev-deploy
    fi

    echo "Updating AWS infrastructure."
    stack_name=${PRODUCT_NAME}-${SERVICE_NAME}-pipeline-${environment_name}

    # Create deployment S3 bucket if it doesn't exist
    if aws s3api head-bucket --bucket ${deploy_bucket_name} 2>/dev/null; then
        echo S3 bucket ${deploy_bucket_name} already exists. Not creating it.
    else
        aws s3api create-bucket --bucket ${deploy_bucket_name}
        echo Created S3 bucket: ${deploy_bucket_name}.
    fi

    # Combine the base cloudformation template with the appropriate stack-type specific template
    # The weird "<(echo)" in the following command is to insert a newline between the two file contents
    cat cloudformation/base.yaml <(echo) cloudformation/${STACK_TYPE}.yaml > combined-${STACK_TYPE}.yaml

    # Package and upload the lambdas and create the modified Cloudformation template
    deploy_bucket_prefix=${environment_name}-${PRODUCT_NAME}-${SERVICE_NAME}-deploy
    aws cloudformation package \
        --template-file combined-${STACK_TYPE}.yaml \
        --output-template-file combined-${STACK_TYPE}.packaged.yaml \
        --s3-prefix ${deploy_bucket_prefix} \
        --s3-bucket ${deploy_bucket_name}

    # Deploy the stack
    aws cloudformation deploy \
        --stack-name $stack_name \
        --template-file combined-${STACK_TYPE}.packaged.yaml \
        --capabilities CAPABILITY_NAMED_IAM \
        --parameter-overrides \
            ProductName=${PRODUCT_NAME} \
            ServiceName=${SERVICE_NAME} \
            EnvironmentName=${environment_name} \
            TrainingDataS3Key=${PIPELINE_TRIGGER_S3_KEY}

    # Exit if the deployment failed
    if [ $? -ne 0 ]
    then
        exit 255
    fi
else
    echo "Not updating AWS infrastructure for branch ${GIT_BRANCH}. AWS infrastructure is only updated on master and develop branch commits."
fi


# ------------- Zip Source Code and Upload to S3 -------------
bucket_name=e1-${environment_name}-${PRODUCT_NAME}-${SERVICE_NAME}-source-code
zip_bundle_name=${GIT_COMMIT}.zip
zip -r ${zip_bundle_name} ..
aws s3 cp ${zip_bundle_name} s3://${bucket_name}/${zip_bundle_name}

# ------------- Upload Docker Image to ECR -------------
# Push to the appropriate ECR repo depending on git branch
if [ ${GIT_BRANCH} = ${develop_branch_name} ] || [ ${GIT_BRANCH} = ${master_branch_name} ]; then
    image=${environment_name}-${PRODUCT_NAME}-${SERVICE_NAME}-master
else
    # Pull request
    image=${environment_name}-${PRODUCT_NAME}-${SERVICE_NAME}-staging
fi

chmod +x ../container/algorithm/test

# Get the account number associated with the current IAM credentials
account=$(aws sts get-caller-identity --query Account --output text)

if [ $? -ne 0 ]
then
    exit 255
fi


region=${region:-$AWS_REGION}

fullname="${account}.dkr.ecr.${region}.amazonaws.com/${image}:${GIT_COMMIT}"

# Get the login command from ECR and execute it directly
$(aws ecr get-login --region ${region} --no-include-email)

# Tag the image with the full name, and push it to ECR
docker tag python-sagemaker-base ${fullname}

docker push ${fullname}
