import json
import boto3
from botocore.exceptions import ClientError
import os
from dateutil.tz import tzlocal

DATA_SOURCE_BUCKET_NAME = os.getenv('DATA_SOURCE_BUCKET_NAME')
DATA_SOURCE_OBJECT_KEY = os.getenv('DATA_SOURCE_OBJECT_KEY')
DEVELOP_BRANCH_ECR_REPOSITORY_NAME = os.getenv('DEVELOP_BRANCH_ECR_REPOSITORY_NAME')

s3 = boto3.resource('s3')
ecr = boto3.client('ecr')

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
        request_params = s3_event['detail']['requestParameters']

        return {
            'bucket_name': request_params['bucketName'],
            'key': request_params['key'],
            'version': s3_event['detail']['responseElements']['x-amz-version-id']
        }

    @staticmethod
    def get_ecr_image_info(ecr_event):
        request_params = ecr_event['detail']['requestParameters']

        return {
            'repository_name': request_params['repositoryName'],
            'image_tags': [request_params['imageTag']]
        }

class S3Client:
    @staticmethod
    def __object_exists(bucket, key):
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
        if bucket is None or key is None:
            print('Must supply bucket and key names')
            return None

        if S3Client.__object_exists(bucket, key):
            s3Object = s3.Object(bucket, key)
            version = s3Object.version_id
        else:
            version = None
        return version

    @staticmethod
    def get_source_object_info(bucket, key):
        version = S3Client.__get_current_object_version(bucket, key)

        if not version:
            return None
        else:
            return {
                'bucket_name': bucket,
                'key': key,
                'version': version
            }

class EcrClient:
    @staticmethod
    def __get_image_details(repository_name):
        try:
            response = ecr.describe_images(repositoryName=repository_name)
            return response.get('imageDetails')
        except ClientError as e:
            if e.response['Error']['Code'] == "RepositoryNotFoundException":
                print(e.response['Error']['Message'])
                return None
            else:
                # Something else has gone wrong.
                raise

    @staticmethod
    def __get_latest_image(image_details):
        if len(image_details) > 0:
            return sorted(image_details, key = lambda x: x['imagePushedAt'], reverse=True)[0]
        else:
            return None

    @staticmethod
    def __get_latest_image_tags(repository_name):
        image_details = EcrClient.__get_image_details(repository_name)
        if image_details is None:
            return None
        else:
            latest_image = EcrClient.__get_latest_image(image_details)
            return None if not latest_image else latest_image.get('imageTags')

    @staticmethod
    def get_ecr_image_info(repository_name):
        if not repository_name:
            return None

        image_tags = EcrClient.__get_latest_image_tags(repository_name)
        if image_tags:
            return {
                'repository_name': repository_name,
                'image_tags': image_tags
            }
        else:
            return None

def log_and_return_input(input):
    print(input)
    return input

def lambda_handler(event, context):
    print('Received event: {}'.format(event))

    # Make sure environment variables are populated
    if None in [DATA_SOURCE_BUCKET_NAME, DATA_SOURCE_OBJECT_KEY, DEVELOP_BRANCH_ECR_REPOSITORY_NAME]:
        return log_and_return_input({
            'statusCode': 500,
            'body': json.dumps('Environment variables not populated.')
        })

    if EventParser.is_new_data_event(event):
        # Get latest data version
        s3_info = EventParser.get_source_object_info(event)
        ecr_info = EcrClient.get_ecr_image_info(DEVELOP_BRANCH_ECR_REPOSITORY_NAME)
    elif EventParser.is_new_ecr_image_event(event):
        s3_info = S3Client.get_source_object_info(DATA_SOURCE_BUCKET_NAME, DATA_SOURCE_OBJECT_KEY)
        # Get latest "develop" branch ECR image
        ecr_info = EventParser.get_ecr_image_info(event)
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

    return log_and_return_input({
        'statusCode': 200,
        'body': json.dumps({
            's3': s3_info,
            'ecr': ecr_info
        })
    })