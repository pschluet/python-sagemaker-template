import json
import boto3
import uuid
from zipfile import ZipFile
from botocore.exceptions import ClientError
import os
from dateutil.tz import tzlocal
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DATA_SOURCE_BUCKET_NAME = os.getenv('DATA_SOURCE_BUCKET_NAME')
SOURCE_CODE_BUCKET_NAME = os.getenv('SOURCE_CODE_BUCKET_NAME')
DATA_SOURCE_OBJECT_KEY = os.getenv('DATA_SOURCE_OBJECT_KEY')
MASTER_ECR_REPOSITORY_NAME = os.getenv('MASTER_ECR_REPOSITORY_NAME')
STEP_FUNCTIONS_STATE_MACHINE_ARN = os.getenv('STEP_FUNCTIONS_STATE_MACHINE_ARN')

s3 = boto3.resource('s3')
s3_client = boto3.client('s3')
ecr = boto3.client('ecr')
sfn = boto3.client('stepfunctions')

def generate_file_path(path):
    """Prepend all file paths with "/tmp/" because that is the only place we can write to in an AWS Lambda
    
    Arguments:
        path {string} -- the file path 
    
    Returns:
        string -- the input file path prepended with "/tmp/"
    """
    return '/tmp/' + path

class EventParser:
    @staticmethod
    def __does_event_have_event_source(event, desired_event_source):
        """Check if the event's "eventSource" is equal to the desired event source
        
        Arguments:
            event {dict} -- the Cloudwatch event that triggered this lambda
            desired_event_source {string} -- the event source that you want to compare against
        
        Returns:
            bool -- True if the event source is equal to the desired event source, else false
        """
        try:
            event_source = event['detail']['eventSource']
        except (KeyError, AttributeError):
            return False
            
        return event_source == desired_event_source
    
    @staticmethod
    def is_new_ecr_image_event(event):
        """Check if this event was triggered by Amazon ECR
        
        Arguments:
            event {dict} -- the Cloudwatch event that triggered this lambda
        
        Returns:
            bool -- True if the event was triggered by ECR, else false
        """
        return EventParser.__does_event_have_event_source(event, 'ecr.amazonaws.com')
    
    @staticmethod
    def is_new_data_event(event):
        """Check if this event was triggered by Amazon S3
        
        Arguments:
            event {dict} -- the Cloudwatch event that triggered this lambda
        
        Returns:
            bool -- True if the event was triggered by S3, else false
        """
        return EventParser.__does_event_have_event_source(event, 's3.amazonaws.com')

    @staticmethod
    def get_source_object_info(s3_event):
        """Get information regarding the training data source file in S3
        
        Arguments:
            s3_event {dict} -- the Cloudwatch S3 event that triggered this lambda
        
        Returns:
            dict -- version information regarding the training data source file in S3
        """
        request_params = s3_event['detail']['requestParameters']

        return {
            'bucket_name': request_params['bucketName'],
            'key': request_params['key'],
            'version': s3_event['detail']['responseElements']['x-amz-version-id']
        }

    @staticmethod
    def get_ecr_image_info(ecr_event):
        """Get information regarding the training docker image in ECR
        
        Arguments:
            s3_event {dict} -- the Cloudwatch ECR event that triggered this lambda
        
        Returns:
            dict -- version information regarding the training docker image in ECR
        """
        request_params = ecr_event['detail']['requestParameters']

        return {
            'repository_name': request_params['repositoryName'],
            'image_tags': [request_params['imageTag']]
        }

class S3Client:
    @staticmethod
    def __object_exists(bucket, key):
        """Check if a particular S3 object exists
        
        Arguments:
            bucket {string} -- the S3 bucket to check
            key {string} -- the S3 key to check
        
        Returns:
            bool -- True if it exists, else false
        """
        try:
            s3.Object(bucket, key).load()
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == "404":
                return False
            else:
                # Something else has gone wrong.
                raise

    @staticmethod
    def __get_current_object_version(bucket, key):
        """Get the version of the S3 object
        
        Arguments:
            bucket {string} -- the S3 bucket to check
            key {string} -- the S3 key to check
        
        Returns:
            string -- version of the file in S3
        """
        if bucket is None or key is None:
            logger.error('Must supply bucket and key names')
            return None

        if S3Client.__object_exists(bucket, key):
            s3Object = s3.Object(bucket, key)
            version = s3Object.version_id
        else:
            version = None
        return version

    @staticmethod
    def get_source_object_info(bucket, key):
        """Get information regarding the training data source file in S3
        
        Arguments:
            bucket {string} -- the S3 bucket to check
            key {string} -- the S3 key to check
        
        Returns:
            dict -- version information regarding the training data source file in S3
        """
        version = S3Client.__get_current_object_version(bucket, key)

        if not version:
            return None
        else:
            return {
                'bucket_name': bucket,
                'key': key,
                'version': version
            }
        
    @staticmethod
    def download_file(bucket_name, object_name, new_file_path):
        """Download a file from S3
        
        Arguments:
            bucket_name {string} -- the name of the S3 bucket where the file is stored
            object_name {string} -- the S3 key for the file/object
            new_file_path {string} -- the local path where you want to store the downloaded file
        
        Returns:
            bool -- True if successful, else throws an exception
        """
        try:
            with open(new_file_path, 'wb') as f:
                s3_client.download_fileobj(bucket_name, object_name, f)
        except ClientError as e:
            logger.error('Error retreiving source code bundle from {}: {}'.format(bucket_name + '/' + object_name, e.response['Error']['Message']))
            raise
        return True

class EcrClient:
    @staticmethod
    def __get_image_details(repository_name):
        """Get details about all the images in an ECR repository
        
        Arguments:
            repository_name {string} -- ECR repository name
        
        Returns:
            list -- list of attributes for each image in the repository
        """
        try:
            response = ecr.describe_images(repositoryName=repository_name)
            return response.get('imageDetails')
        except ClientError as e:
            if e.response['Error']['Code'] == "RepositoryNotFoundException":
                logger.error(e.response['Error']['Message'])
                return None
            else:
                # Something else has gone wrong.
                raise

    @staticmethod
    def __get_latest_image(image_details):
        """Get attributes about the ECR image that was uploaded most recently
        
        Arguments:
            image_details {list} -- a list of details regarding ECR images
        
        Returns:
            dict -- attributes about the ECR image that was uploaded to ECR most recently
        """
        if len(image_details) > 0:
            return sorted(image_details, key = lambda x: x['imagePushedAt'], reverse=True)[0]
        else:
            return None

    @staticmethod
    def __get_latest_image_tags(repository_name):
        """Get the image tags from the most recent ECR image
        
        Arguments:
            repository_name {string} -- the ECR repository name
        
        Returns:
            list -- a list of string tags
        """
        image_details = EcrClient.__get_image_details(repository_name)
        if image_details is None:
            return None
        else:
            latest_image = EcrClient.__get_latest_image(image_details)
            return None if not latest_image else latest_image.get('imageTags')

    @staticmethod
    def get_ecr_image_info(repository_name):
        """Get information regarding the latest training docker image in the ECR repository
        
        Arguments:
            repository_name {string} -- the ECR repository name
        
        Returns:
            dict -- version information regarding the training docker image in ECR
        """
        if not repository_name:
            return None

        image_tags = EcrClient.__get_latest_image_tags(repository_name)
        repository_uri = EcrClient.get_repository_uri(repository_name)

        if image_tags and repository_uri:
            return {
                'repository_name': repository_name,
                'image_uri': repository_uri + ':' + image_tags[0],
                'image_tags': image_tags
            }
        else:
            return None

    @staticmethod
    def get_repository_uri(repository_name):
        """Get the full URI for a repository
        
        Arguments:
            repository_name {string} -- the repository name
        
        Returns:
            string -- repository URI 
        """
        try:
            repositories = ecr.describe_repositories()
            uri_list = [x['repositoryUri'] for x in repositories['repositories'] if x['repositoryName'] == repository_name]
            if uri_list:
                return uri_list[0]
            else:
                logger.error('Could not get repository URI for {}. There was no repository with that name.')
                return None
        except ClientError as e:
            logger.error('Could not get repository URI for {}: {}.'.format(repository_name, e))
            return None
        except KeyError as e:
            logger.error('Could not get repository URI for {}. AWS response did not contain repository information.'.format(repository_name))
            return None

class EcrService:

    @staticmethod
    def get_ecr_info_from_event(ecr_event):
        """Get ECR image version information from an ECR Cloudwatch event
        
        Arguments:
            ecr_event {dict} -- the ECR Cloudwatch event that triggered this Lambda
        
        Returns:
            dict -- ECR version information
        """
        ecr_info = EventParser.get_ecr_image_info(ecr_event)

        if ecr_info:
            repository_uri = EcrClient.get_repository_uri(ecr_info['repository_name'])
            ecr_info['image_uri'] = repository_uri + ':' + ecr_info['image_tags'][0]
            return ecr_info
        else:
            return None

    @staticmethod
    def get_ecr_info_from_repo_name(repository_name):
        """Get ECR image version information from an ECR repository name
        
        Arguments:
            repository_name {string} -- the name of the ECR repository
        
        Returns:
            dict -- ECR version information
        """
        return EcrClient.get_ecr_image_info(repository_name)

class StepFuncClient:

    @staticmethod
    def start_execution(input_data):
        """Start a step-functions workflow
        
        Arguments:
            input_data -- the input data to pass to the first state of the step functions state machine
        
        Returns:
            [dict] -- dict with keys 'success' (boolean) indicating success/failure, 'message' with details
                      about the success or failure, and 'execution_name' with the step functions execution
                      name
        """

        # Start execution of AWS Step Functions state machine
        execution_name = str(uuid.uuid1())

        try:
            sfn_response = sfn.start_execution(
                stateMachineArn=STEP_FUNCTIONS_STATE_MACHINE_ARN,
                name=execution_name,
                input=json.dumps(input_data)
            )
            response = {
                'success': True,
                'message': 'Successfully started step function execution {} at {} with input data {}'.format(
                    sfn_response['executionArn'],
                    sfn_response['startDate'],
                    input_data,                
                ),
                'execution_name': execution_name
            }
            logger.info(response['message'])
        except ClientError as e:
            response = {
                'success': False,
                'message': 'Error starting step function execution {}. {}: {}'.format(
                    execution_name,
                    e.response['Error']['Code'],
                    e.response['Error']['Message']
                )
            }
            logger.error(response['message'])

        return response

class SourceCodeRepository:
    def __init__(self, s3_bucket_name, s3_object_name):
        """Initialize the repository by downloading the source code from S3 and unzipping it to local storage
        
        Arguments:
            s3_bucket_name {string} -- the name of the S3 bucket where the source code zip bundle is stored
            s3_object_name {string} -- the S3 key for the source code zip file/object
        """
        self.init_success = False
        # Get source code from S3 bucket
        src_code_zip_file_name = s3_object_name
        S3Client.download_file(
            bucket_name=s3_bucket_name, 
            object_name=s3_object_name, 
            new_file_path=generate_file_path(src_code_zip_file_name)
        )

        # Unzip source code
        with ZipFile(generate_file_path(src_code_zip_file_name), 'r') as f:
            f.extractall(generate_file_path(''))

        self.init_success = True

    def __get_hyperparameters(self):
        """Retrieve the hyperparameters from the local test directory
        
        Returns:
            dict -- the SageMaker hyperparameters, or None if unsuccessful
        """
        if not self.init_success: return None

        file_path = generate_file_path('container/local_test/test_dir/input/config/hyperparameters.json')

        try:
            with open(file_path) as f:
                hyperparameters = json.load(f)
        except Exception as e:
            logger.error('Error retrieving SageMaker settings from {}. {}'.format(file_path, e))
            return None

        return hyperparameters

    def get_sagemaker_settings(self):
        """Retrieve the SageMaker training/deployment settings from the config. file
        
        Returns:
            dict -- the SageMaker training/deployment settings, or None if unsuccessful
        """
        if not self.init_success: return None

        file_path = generate_file_path('deploy/sagemaker-settings.json')

        try:
            with open(file_path) as f:
                settings = json.load(f)
        except Exception as e:
            logger.error('Error retrieving SageMaker settings from {}. {}'.format(file_path, e))
            return None

        # Get hyperparameters from a different file
        settings['TrainingJob']['HyperParameters'] = self.__get_hyperparameters()

        return settings

def log_and_return_input(input):
    """Log the input object and return it. Convenience function
    
    Arguments:
        input -- input object to log
    
    Returns:
        The same object that was passed as input
    """
    logger.info(input)
    return input

def lambda_handler(event, context):
    """The main entrypoint to the lambda function
    
    Arguments:
        event {dict} -- the event that triggered the lambda
        context -- lambda context
    
    Returns:
        dict -- a dict with a status code and response body
    """
    logger.info('Received event: {}'.format(event))

    # Make sure environment variables are populated
    if None in [DATA_SOURCE_BUCKET_NAME, DATA_SOURCE_OBJECT_KEY, MASTER_ECR_REPOSITORY_NAME, STEP_FUNCTIONS_STATE_MACHINE_ARN, SOURCE_CODE_BUCKET_NAME]:
        return log_and_return_input({
            'statusCode': 500,
            'body': json.dumps('Environment variables not populated.')
        })

    if EventParser.is_new_data_event(event):
        # Get latest data version
        s3_info = EventParser.get_source_object_info(event)
        ecr_info = EcrService.get_ecr_info_from_repo_name(MASTER_ECR_REPOSITORY_NAME)
    elif EventParser.is_new_ecr_image_event(event):
        s3_info = S3Client.get_source_object_info(DATA_SOURCE_BUCKET_NAME, DATA_SOURCE_OBJECT_KEY)
        # Get latest "develop" branch ECR image
        ecr_info = EcrService.get_ecr_info_from_event(event)
    else:
        return log_and_return_input({
            'statusCode': 400,
            'body': json.dumps('Received unrecognized event.')
        })

    if not s3_info:
        return log_and_return_input({
            'statusCode': 404,
            'body': json.dumps('S3 data source could not be retrieved.')
        })

    if not ecr_info:
        return log_and_return_input({
            'statusCode': 404,
            'body': json.dumps('ECR image could not be retrieved.')
        })

    # Get SageMaker settings from source code
    source_code_repository = SourceCodeRepository(
        s3_bucket_name=SOURCE_CODE_BUCKET_NAME,
        s3_object_name='{}.zip'.format(ecr_info['image_tags'][0])
    )
    sagemaker_settings = source_code_repository.get_sagemaker_settings()
    if sagemaker_settings is None:
        return log_and_return_input({
            'statusCode': 404,
            'body': json.dumps('Could not retrieve SageMaker settings.')
        })

    # Start execution of AWS Step Functions state machine
    state_machine_input = {
        's3': s3_info,
        'ecr': ecr_info,
        'sagemaker': sagemaker_settings
    }
    step_func_response = StepFuncClient.start_execution(state_machine_input)

    return log_and_return_input({
        'statusCode': 200 if step_func_response['success'] else 500,
        'body': step_func_response['message']
    })