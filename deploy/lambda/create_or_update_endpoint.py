import boto3
import os
import json
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sagemaker = boto3.client('sagemaker')

ENDPOINT_NAME = os.getenv('ENDPOINT_NAME')
PRODUCT_TAG_VALUE = os.getenv('PRODUCT_TAG_VALUE')
SERVICE_TAG_VALUE = os.getenv('SERVICE_TAG_VALUE')
STAGE_TAG_VALUE = os.getenv('STAGE_TAG_VALUE')

class SageMakerClient:
    @staticmethod
    def __endpoint_exists(endpoint_name):
        """Check if a SageMaker endpoint exists with the given name
        
        Arguments:
            endpoint_name {string} -- the name to check
        
        Returns:
            bool -- True if the endpoint exists, else False
        """
        try:
            sagemaker.describe_endpoint(EndpointName=endpoint_name)
            return True
        except ClientError as e:
            return False

    @staticmethod
    def create_or_update_endpoint(endpoint_name, endpoint_config_name, tags):
        """Create a SageMaker endpoint, or, if it already exists, update the existing endpoint
        
        Arguments:
            endpoint_name {string} -- the SageMaker endpoint name
            endpoint_config_name {string} -- the SageMaker endpoint config name
            tags {dict} -- the tags to tag the new endpoint with
        
        Returns:
            dict -- a dict with the endpoint ARN (key "EndpointArn")
        """
        if SageMakerClient.__endpoint_exists(endpoint_name):
            response = sagemaker.update_endpoint(
                EndpointName=endpoint_name,
                EndpointConfigName=endpoint_config_name
            )
        else:
            response = sagemaker.create_endpoint(
                EndpointName=endpoint_name,
                EndpointConfigName=endpoint_config_name,
                Tags=tags
            )

        return response

def lambda_handler(event, context):
    """The main entrypoint to the lambda function
    
    Arguments:
        event {dict} -- the event that triggered the lambda
        context -- lambda context
    
    Returns:
        dict -- a dict with the endpoint ARN (key "EndpointArn")
    """
    logger.info(f'event: {event}')
    response = SageMakerClient.create_or_update_endpoint(
        endpoint_name=ENDPOINT_NAME,
        endpoint_config_name=event['endpoint_config_name'],
        tags=[
            {
                'Key': 'product',
                'Value': PRODUCT_TAG_VALUE
            },
            {
                'Key': 'service',
                'Value': SERVICE_TAG_VALUE
            },
            {
                'Key': 'stage',
                'Value': STAGE_TAG_VALUE
            }
        ]
    )
    return response