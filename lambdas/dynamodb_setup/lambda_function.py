from datetime import datetime, timedelta
import boto3
from boto3.dynamodb.conditions import Key
import textwrap

def lambda_handler(event, context):
    source_athena_table_name=f"{event['database']}.{event['table']}"
    dynamodb = boto3.resource('dynamodb')
    last_update_time_table = dynamodb.Table(f"dynamodb-etl-orchestrator-last-update-time-{event['env']}")
    try:
        response = last_update_time_table.query(KeyConditionExpression=Key('source_athena_table_name').eq(source_athena_table_name))
        last_successful_run_timestamp = (datetime.strptime(response['Items'][0]['last_successful_run_timestamp'],"%Y-%m-%d %H:%M:%S")- timedelta(hours = 6)).strftime("%Y-%m-%d %H:%M:%S")
    except:
        last_successful_run_timestamp = datetime.utcnow() - timedelta(days = 30) 
        last_successful_run_timestamp = last_successful_run_timestamp.strftime("%Y-%m-%d %H:%M:%S")
    event['current_timestamp']=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    event['last_successful_run_timestamp']=last_successful_run_timestamp
    event['query_string']=textwrap.dedent(f"""
        SELECT * FROM {source_athena_table_name}
        WHERE cast({event['time_stamp_column_name']} as TIMESTAMP) >= cast('{last_successful_run_timestamp}' as TIMESTAMP)""")
    now = datetime.utcnow()
    year=now.strftime("%Y")
    month=now.strftime("%m")
    day=now.strftime("%d")
    hour=now.strftime("%H")
    if event['lambda_name']!='' or event['ecr_repo_name']!='':
        event['Bucket']=f"pbr-data-lake-{event['env']}"
        location_indicator=event['lambda_name'] if event['lambda_name']!='' else event['ecr_repo_name']
        event['Key']=f"data/raw/{location_indicator}/{year}/{month}/{day}/{hour}/updated_{location_indicator}.csv"
    return event