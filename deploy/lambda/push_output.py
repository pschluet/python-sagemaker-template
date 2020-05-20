import boto3
import os
import logging
import json
import tempfile
import tarfile
from concurrent.futures import ThreadPoolExecutor, wait
from io import BytesIO

logger = logging.getLogger()
logger.setLevel(logging.INFO)

OUTPUT_BUCKET_NAME = os.getenv('OUTPUT_BUCKET_NAME')
DESTINATION_PREFIX = 'result'

class S3Client:
    def __init__(self):
        self.__s3 = boto3.resource('s3')
        self.__bucket = self.__s3.Bucket(OUTPUT_BUCKET_NAME)

    def delete_objects_with_prefix(self, prefix):
        """Delete all S3 objects in OUTPUT_BUCKET_NAME whose keys start with the given prefix
        
        Arguments:
            prefix {string} -- the S3 key prefix
        
        Returns:
            object -- the response from S3
        """
        objects_to_delete = self.__bucket.objects.filter(Prefix=prefix)
        key_list = [x.key for x in objects_to_delete.all()]
        logger.info(f'Deleting the following objects: {key_list}')
        return objects_to_delete.delete()

    def copy_object(self, source_key, destination_key):
        """Copy an object in OUTPUT_BUCKET_NAME
        
        Arguments:
            source_key {string} -- the S3 key of the source data
            destination_key {string} -- the S3 key of the destination data
        
        Returns:
            object -- the response from S3
        """
        source_object_info = {
            'Bucket': OUTPUT_BUCKET_NAME,
            'Key': source_key
        }
        logger.info(f'Copying {source_key} to {destination_key}')
        return self.__bucket.copy(source_object_info, destination_key)

    def create_object(self, key, contents):
        """Create an object in the OUTPUT_BUCKET_NAME S3 bucket
        
        Arguments:
            key {string} -- the S3 key
            contents {string} -- the S3 object contents
        
        Returns:
            object -- the response from S3
        """
        logger.info(f'Creating object - Key: {key}, Value: {contents}')
        return self.__bucket.put_object(
            Body=contents,
            Key=key
        )

    def unzip_tarfile(self, source_key, destination_key_prefix, delete_source_file=False):
        """Unzip a gzipped tarfile (.tar.gz) file in S3
        
        Arguments:
            source_key {string} -- the S3 key of the source file (should end in .tar.gz)
            destination_key_prefix {string} -- the destination for the unzipped files. The
                keys of the unzipped files will be the destination key prefix concatenated
                with the file name from the archive (e.g. <destination_key_prefix><file_one_name>,
                <destination_key_prefix><file_two_name>, etc.)
            delete_source_file {boolean} -- True if you want to delete the source file, otherwise False
                default is False
        Returns:
            boolean -- True if extraction successful, else False
        """
        # Fetch and load source file
        try:
            temp_file = tempfile.NamedTemporaryFile()
            self.__bucket.download_file(source_key, temp_file.name)
            tar_file = tarfile.open(temp_file.name)
        except Exception as e:
            logger.error(f'Could not download or open source file {source_key}. {e}')
            raise e

        # Extract files and stream them to S3
        success = True
        for file_name in tar_file.getnames():
            success &= self.__extract(tar_file, file_name, destination_key_prefix)
            if not success:
                tar_file.close()
                return False
        
        tar_file.close()

        if delete_source_file:
            self.delete_objects_with_prefix(source_key)

        return True

    def __extract(self, tar_file, file_name_to_extract, destination_key_prefix):
        """Extract a file from a tar archive and upload it to S3
        
        Arguments:
            tar_file {string} -- the name of the file in the tar archive
            file_name_to_extract {string} -- the name of the file in the tar archive
            destination_key_prefix {string} -- the S3 prefix for the extracted file
        
        Returns:
            boolean -- True if extraction succeeds, else False
        """
        try:
            self.__bucket.upload_fileobj(
                Fileobj=tar_file.extractfile(file_name_to_extract),
                Key=os.path.join(destination_key_prefix, file_name_to_extract)
            )
            logger.info(f'Extracted {file_name_to_extract}.')
        except Exception as e:
            logger.error(f'Failed to extract {file_name_to_extract}. {e}')
            return False

        return True

class EventParser:
    def __init__(self, event):
        self.__event = event

    def get_sagemaker_output_key(self):
        """Get the S3 key that represents the output from the SageMaker training job
           in the step functions workflow that started this lambda
        
        Returns:
            string -- the S3 key
        """
        model_artifacts_zip_url = self.__event['PreviousStep']['ModelArtifacts']['S3ModelArtifacts']
        output_zip_url = model_artifacts_zip_url.replace('model.tar.gz', 'output.tar.gz')
        return output_zip_url.replace(f's3://{OUTPUT_BUCKET_NAME}/','')


def lambda_handler(event, context):
    """The main entrypoint to the lambda function
    
    Arguments:
        event {dict} -- the event that triggered the lambda
        context -- lambda context
    
    Returns:
        dict -- a dict with the lambda response
    """
    logger.info(f'event: {event}')

    s3 = S3Client()
    event_parser = EventParser(event)

    # Copy result zip to final destination
    extraction_successful = s3.unzip_tarfile(
        source_key=event_parser.get_sagemaker_output_key(),
        destination_key_prefix=DESTINATION_PREFIX,
        delete_source_file=False
    )

    # Update the file that shows where the output.tar.gz came from
    if extraction_successful:
        create_result = s3.create_object(
            key=f'{DESTINATION_PREFIX}/output_source.txt',
            contents=f'The data files in this folder came from {event_parser.get_sagemaker_output_key()}'
        )
    else:
        create_result = s3.create_object(
            key=f'{DESTINATION_PREFIX}/error.txt',
            contents=f'There was an error in extracting new data. Some of the data files in this folder may have been overwritten erroneously. Please replace them with the data described in output_source.txt.'
        )

    return {
        'source_key': event_parser.get_sagemaker_output_key(),
        'destination_prefix': DESTINATION_PREFIX
    }