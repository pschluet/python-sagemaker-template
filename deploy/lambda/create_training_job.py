import boto3
import os
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sagemaker = boto3.client('sagemaker')

SAGEMAKER_ROLE_ARN = os.getenv('SAGEMAKER_ROLE_ARN')
OUTPUT_BUCKET_NAME = os.getenv('OUTPUT_BUCKET_NAME')
PRODUCT_TAG_VALUE = os.getenv('PRODUCT_TAG_VALUE')
SERVICE_TAG_VALUE = os.getenv('SERVICE_TAG_VALUE')
STAGE_TAG_VALUE = os.getenv('STAGE_TAG_VALUE')
MASTER_ECR_REPOSITORY_NAME = os.getenv('MASTER_ECR_REPOSITORY_NAME')
STAGING_ECR_REPOSITORY_NAME = os.getenv('STAGING_ECR_REPOSITORY_NAME')

class SageMakerClient:
    @staticmethod
    def create_training_job_request(step_func_input):
        """Create the training job request with parameters from the step function input
        
        Arguments:
            step_func_input {dict} -- input from the step functions workflow
        
        Returns:
            dict -- the SageMaker training job request
        """
        step_function_execution_name = step_func_input['execution_name']
        s3_info = step_func_input['input']['s3']
        ecr_info = step_func_input['input']['ecr']
        sagemaker_settings = step_func_input['input']['sagemaker']

        # Change the prefix for the output s3 bucket depending on which ECR
        # repository triggered the step function workflow
        source_ecr_repo_name = ecr_info['repository_name']
        s3_output_prefix_map = {
            STAGING_ECR_REPOSITORY_NAME: 'staging',
            MASTER_ECR_REPOSITORY_NAME: 'master'
        }

        return {
            'TrainingJobName': step_function_execution_name,
            'HyperParameters': sagemaker_settings['TrainingJob']['HyperParameters'],
            'AlgorithmSpecification': {
                'TrainingImage': ecr_info['image_uri'],
                'TrainingInputMode': 'File',
                'MetricDefinitions': sagemaker_settings['TrainingJob']['MetricDefinitions']
            },
            'RoleArn': SAGEMAKER_ROLE_ARN,
            'InputDataConfig': [
                {
                    'ChannelName': 'train',
                    'DataSource': {
                        'S3DataSource': {
                            'S3DataType': 'S3Prefix',
                            'S3Uri': f"s3://{s3_info['bucket_name']}",
                            'S3DataDistributionType': 'FullyReplicated',
                        }
                    }
                }
            ],
            'OutputDataConfig': {
                'S3OutputPath': f's3://{OUTPUT_BUCKET_NAME}/{s3_output_prefix_map[source_ecr_repo_name]}'
            },
            'ResourceConfig': {
                'InstanceType': sagemaker_settings['TrainingJob']['TrainingResourceConfig']['InstanceType'],
                'InstanceCount': 1,
                'VolumeSizeInGB': sagemaker_settings['TrainingJob']['TrainingResourceConfig']['VolumeSizeInGB'],
            },
            'StoppingCondition': sagemaker_settings['TrainingJob']['StoppingCondition'],
            'EnableNetworkIsolation': True,
            'Tags': [
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
        }

def lambda_handler(event, context):
    """The main entrypoint to the lambda function
    
    Arguments:
        event {dict} -- the event that triggered the lambda
        context -- lambda context
    
    Returns:
        dict -- a dict with a status code and response body
    """
    logger.info(f'event: {event}')
    request = SageMakerClient.create_training_job_request(event)
    return {
        'TrainingJobParameters': request,
        'TrainingJobName': request['TrainingJobName']
    }