import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sagemaker = boto3.client('sagemaker')

def transform_metric_data_list(final_metric_data_list):
    """Change the structure of the FinalMetricDataList from SageMaker describeTrainingJob
    
    Arguments:
        final_metric_data_list {list} -- output from the SageMaker describeTrainingJob API
          for the FinalMetricDataList key
    
    Returns:
        [dict] -- a dict with the metric names as keys and their values as the values
    """
    if final_metric_data_list:
        metrics = {x['MetricName']:x['Value'] for x in final_metric_data_list}
    else:
        metrics = None
    return metrics

def lambda_handler(event, context):
    """The main entrypoint to the lambda function
    
    Arguments:
        event {dict} -- the event that triggered the lambda
        context -- lambda context
    
    Returns:
        dict -- a dict with a status code and response body
    """
    logger.info(f'event: {event}')

    training_job_name = event['PreviousStep']['TrainingJobName']

    job_info = sagemaker.describe_training_job(TrainingJobName=training_job_name)

    logger.info(f'job_info: {job_info}')
    
    return {
        'TrainingJobName': job_info['TrainingJobName'],
        'TrainingJobArn': job_info['TrainingJobArn'],
        'TrainingJobStatus': job_info['TrainingJobStatus'],
        'SecondaryStatus': job_info['SecondaryStatus'],
        'FailureReason': job_info.get('FailureReason',''),
        'Metrics': transform_metric_data_list(job_info.get('FinalMetricDataList', None)),
        'AlgorithmSpecification': job_info.get('AlgorithmSpecification', None),
        'ModelArtifacts': job_info.get('ModelArtifacts', None)
    }