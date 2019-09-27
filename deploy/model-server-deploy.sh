STACK_NAME=model-server-pipeline

aws cloudformation create-stack \
    --stack-name $STACK_NAME \
    --template-body file://model-server.yaml \
    --capabilities CAPABILITY_IAM \
    --parameters file://model-server-parameters.json \
    --capabilities CAPABILITY_NAMED_IAM

aws cloudformation wait stack-create-complete --stack-name $STACK_NAME
