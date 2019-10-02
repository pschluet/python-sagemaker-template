import json
def lambda_handler(event, context):
    print("Event: {}".format(json.dumps(event)))
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }