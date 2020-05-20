import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sagemaker = boto3.client('sagemaker')

ENDPOINT_NAME = os.getenv('ENDPOINT_NAME')

def lambda_handler(event, context):
    """The main entrypoint to the lambda function
    
    Arguments:
        event {dict} -- the event that triggered the lambda
        context -- lambda context
    
    Returns:
        dict -- a dict with a status code and response body
    """
    logger.info(f'event: {event}')

    endpoint_info = sagemaker.describe_endpoint(EndpointName=ENDPOINT_NAME)
    
    return {
        'EndpointName': endpoint_info['EndpointName'],
        'EndpointConfigName': endpoint_info['EndpointConfigName'],
        'EndpointStatus': endpoint_info['EndpointStatus'],
        'FailureReason': endpoint_info.get('FailureReason',None)
    }