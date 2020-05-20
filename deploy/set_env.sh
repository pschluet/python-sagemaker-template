#!/bin/bash

# Uncomment GIT_COMMIT and GIT_BRANCH when deploying locally. These get set 
# automatically in the deployment pipeline
export GIT_COMMIT=73182fc1b13ffe16024f5afdef08e0f6a883730d
export GIT_BRANCH=develop
export AWS_REGION=us-east-1

# Either batch-job or model-server
export STACK_TYPE=model-server
export PRODUCT_NAME=demo
export SERVICE_NAME=model-server
export PIPELINE_TRIGGER_S3_KEY=iris.csv
export AWS_DEFAULT_REGION=$AWS_REGION