def lambda_handler(event, context):
    event['waitSeconds']=event['waitSeconds']*2
    return event