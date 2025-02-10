from airflow import DAG
from airflow.utils.dates import days_ago
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.athena import AthenaOperator
from airflow.providers.amazon.aws.hooks.glue import GlueJobHook
from airflow.exceptions import AirflowException
from datetime import timedelta
import boto3
import json

def notify_failure(context):
    sns_client = boto3.client('sns', region_name='us-east-1')  # Replace with your region
    message = f"DAG: {context['dag'].dag_id}\nTask: {context['task_instance'].task_id}\nState: {context['task_instance'].state}\nError: {context['task_instance'].xcom_pull(task_ids=context['task_instance'].task_id, key='return_value')}"
    sns_client.publish(
        TopicArn='arn:aws:sns:us-east-1:142114255837:dev-test-stack-Topic',  # Replace with your SNS topic ARN
        Message=message,
        Subject='Airflow DAG Failure Notification'
    )

default_args = {
    'owner': 'your_username',
    'depends_on_past': False,
    'email': ['anzhemeng@gmail.com'],  # Replace with your email
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,  # Allow one retry per task
    'retry_delay': timedelta(minutes=1),
    'on_failure_callback': notify_failure,  # Add callback
}


with DAG(
    dag_id='athena_materialized_view_workflow',
    default_args=default_args,
    description='DAG to manage Athena databases and materialized views',
    schedule_interval='@daily',  # Kick off once a day
    start_date=days_ago(1),
    catchup=False,
    tags=['Athena', 'DataProcessing'],
) as dag:

    def initialize(**kwargs):
        print("Initializing the Athena workflow...")

    initialize_task = PythonOperator(
        task_id='initialize',
        python_callable=initialize,
        provide_context=True,
    )

    def check_database_exist(database_name, **kwargs):
        glue = GlueJobHook(aws_conn_id='aws_default').get_conn()
        try:
            response = glue.get_database(Name=database_name)
            if response:
                print(f"Database '{database_name}' exists.")
                return True
        except glue.exceptions.EntityNotFoundException:
            raise AirflowException(f"Database '{database_name}' does not exist.")
        except Exception as e:
            raise AirflowException(f"Error checking database existence: {str(e)}")

    check_database = PythonOperator(
        task_id='check_database_exists',
        python_callable=check_database_exist,
        op_kwargs={
            'database_name': 'facts',  # Replace with your database name
        },
        provide_context=True,
    )

    def check_table_exist(database_name, table_name, **kwargs):
        glue = GlueJobHook(aws_conn_id='aws_default').get_conn()
        try:
            response = glue.get_table(DatabaseName=database_name, Name=table_name)
            if response:
                print(f"Table '{table_name}' exists in database '{database_name}'.")
                return True
        except glue.exceptions.EntityNotFoundException:
            raise AirflowException(f"Table '{table_name}' does not exist in database '{database_name}'.")
        except Exception as e:
            raise AirflowException(f"Error checking table existence: {str(e)}")

    check_table = PythonOperator(
        task_id='check_table_exists',
        python_callable=check_table_exist,
        op_kwargs={
            'database_name': 'dev-test-stack-raw',  # Replace with your database name
            'table_name': 'dev_test_stack_table',  # Replace with your source table name
        },
        provide_context=True,
    )

    create_materialized_view = AthenaOperator(
        task_id='create_materialized_view',
        query="""
            CREATE OR REPLACE VIEW "facts"."dev_test_stack_table_view" AS 
            WITH CTE AS (
            SELECT *, ROW_NUMBER() OVER(PARTITION BY primarykey ORDER BY streaming_timestamp DESC) AS row_num
            FROM "dev-test-stack-raw"."dev_test_stack_table"
            )
            SELECT inpublication, isbn, pagecount,
            price, authors, productcategory,
            dimensions, primarykey, title, 
            streaming_timestamp, brand,
            description, color, bicycletype,
            year, month, day 
            FROM CTE WHERE row_num = 1
        """,
        database='facts',  # Replace with your database name
        output_location='s3://dev-test-stack-crawler-target/QueryResults/',  # Replace with your S3 bucket
        aws_conn_id='aws_default',
        # wait_for_completion=True,
        retries=1,  # Allow one retry
        retry_delay=timedelta(minutes=1),
    )

    initialize_task >> check_database >> check_table >> create_materialized_view