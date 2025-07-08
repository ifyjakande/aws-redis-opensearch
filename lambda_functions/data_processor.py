#!/usr/bin/env python3
"""
Data Processor Lambda Function
Processes data from generator and stores in Redis/OpenSearch
"""

import json
import boto3
import redis
import logging
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from opensearchpy import OpenSearch, RequestsHttpConnection
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class DataProcessor:
    """Process and store data in Redis and OpenSearch"""
    
    def __init__(self):
        self.opensearch_client = None
        self.redis_client = None
        self.ssm_client = boto3.client('ssm')
        self.secrets_client = boto3.client('secretsmanager')
        
    def get_parameter(self, parameter_name: str) -> str:
        """Get parameter from SSM Parameter Store"""
        try:
            response = self.ssm_client.get_parameter(
                Name=parameter_name,
                WithDecryption=True
            )
            return response['Parameter']['Value']
        except ClientError as e:
            logger.error(f"Error getting parameter {parameter_name}: {str(e)}")
            raise
    
    def get_secret(self, secret_name: str) -> Dict[str, str]:
        """Get secret from AWS Secrets Manager"""
        try:
            response = self.secrets_client.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
        except ClientError as e:
            logger.error(f"Error getting secret {secret_name}: {str(e)}")
            raise
    
    def get_opensearch_client(self) -> OpenSearch:
        """Initialize OpenSearch client"""
        if self.opensearch_client is None:
            try:
                # Get OpenSearch endpoint from environment or parameter store
                endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
                if not endpoint:
                    project_name = os.environ.get('PROJECT_NAME', 'opensearch-redis-pipeline')
                    environment = os.environ.get('ENVIRONMENT', 'dev')
                    endpoint = self.get_parameter(f'/{project_name}/{environment}/opensearch/endpoint')
                
                # Remove https:// if present
                if endpoint.startswith('https://'):
                    endpoint = endpoint[8:]
                
                self.opensearch_client = OpenSearch(
                    hosts=[{'host': endpoint, 'port': 443}],
                    http_compress=True,
                    use_ssl=True,
                    verify_certs=True,
                    ssl_assert_hostname=False,
                    ssl_show_warn=False,
                    connection_class=RequestsHttpConnection,
                    timeout=60,
                    max_retries=3,
                    retry_on_timeout=True
                )
                
                logger.info(f"OpenSearch client initialized for endpoint: {endpoint}")
                
            except Exception as e:
                logger.error(f"Error initializing OpenSearch client: {str(e)}")
                raise
                
        return self.opensearch_client
    
    def get_redis_client(self) -> redis.Redis:
        """Initialize Redis client"""
        if self.redis_client is None:
            try:
                # Get Redis connection details
                endpoint = os.environ.get('REDIS_ENDPOINT')
                port = int(os.environ.get('REDIS_PORT', 6379))
                
                if not endpoint:
                    project_name = os.environ.get('PROJECT_NAME', 'opensearch-redis-pipeline')
                    environment = os.environ.get('ENVIRONMENT', 'dev')
                    endpoint = self.get_parameter(f'/{project_name}/{environment}/redis/endpoint')
                    port = int(self.get_parameter(f'/{project_name}/{environment}/redis/port'))
                
                # Get auth token if available
                auth_token = None
                try:
                    project_name = os.environ.get('PROJECT_NAME', 'opensearch-redis-pipeline')
                    environment = os.environ.get('ENVIRONMENT', 'dev')
                    secret_name = f'{project_name}-{environment}-redis-auth-token'
                    secret = self.get_secret(secret_name)
                    auth_token = secret.get('auth-token')
                except:
                    logger.warning("No Redis auth token found, connecting without authentication")
                
                # Initialize Redis client
                self.redis_client = redis.Redis(
                    host=endpoint,
                    port=port,
                    password=auth_token,
                    decode_responses=True,
                    ssl=True,
                    ssl_cert_reqs=None,
                    socket_connect_timeout=10,
                    socket_timeout=10,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                
                # Test connection
                self.redis_client.ping()
                logger.info(f"Redis client initialized for endpoint: {endpoint}:{port}")
                
            except Exception as e:
                logger.error(f"Error initializing Redis client: {str(e)}")
                raise
                
        return self.redis_client
    
    def create_opensearch_indices(self):
        """Create OpenSearch indices if they don't exist"""
        opensearch_client = self.get_opensearch_client()
        
        # User events index
        user_events_mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "session_id": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "event_type": {"type": "keyword"},
                    "product_id": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "price": {"type": "double"},
                    "quantity": {"type": "integer"},
                    "currency": {"type": "keyword"},
                    "user_agent": {"type": "text"},
                    "ip_address": {"type": "ip"},
                    "location": {
                        "properties": {
                            "city": {"type": "keyword"},
                            "state": {"type": "keyword"},
                            "country": {"type": "keyword"}
                        }
                    },
                    "device_type": {"type": "keyword"},
                    "referrer": {"type": "keyword"},
                    "page_url": {"type": "keyword"},
                    "revenue": {"type": "double"},
                    "search_query": {"type": "text"},
                    "search_results_count": {"type": "integer"},
                    "rating": {"type": "integer"},
                    "review_text": {"type": "text"},
                    "payment_method": {"type": "keyword"},
                    "discount_applied": {"type": "boolean"},
                    "discount_amount": {"type": "double"}
                }
            }
        }
        
        # Product catalog index
        product_catalog_mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "name": {"type": "text"},
                    "category": {"type": "keyword"},
                    "subcategory": {"type": "keyword"},
                    "price": {"type": "double"},
                    "currency": {"type": "keyword"},
                    "brand": {"type": "keyword"},
                    "description": {"type": "text"},
                    "tags": {"type": "keyword"},
                    "stock_quantity": {"type": "integer"},
                    "weight": {"type": "double"},
                    "dimensions": {
                        "properties": {
                            "length": {"type": "double"},
                            "width": {"type": "double"},
                            "height": {"type": "double"}
                        }
                    },
                    "rating": {"type": "double"},
                    "review_count": {"type": "integer"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "is_active": {"type": "boolean"},
                    "image_url": {"type": "keyword"}
                }
            }
        }
        
        # Create indices
        indices = [
            ('user-events', user_events_mapping),
            ('product-catalog', product_catalog_mapping)
        ]
        
        for index_name, mapping in indices:
            try:
                if not opensearch_client.indices.exists(index=index_name):
                    opensearch_client.indices.create(
                        index=index_name,
                        body=mapping
                    )
                    logger.info(f"Created OpenSearch index: {index_name}")
                else:
                    logger.info(f"OpenSearch index already exists: {index_name}")
            except Exception as e:
                logger.error(f"Error creating index {index_name}: {str(e)}")
                raise
    
    def process_user_events(self, events: List[Dict[str, Any]]) -> int:
        """Process user events and store in Redis and OpenSearch"""
        opensearch_client = self.get_opensearch_client()
        redis_client = self.get_redis_client()
        
        processed_count = 0
        bulk_actions = []
        
        for event in events:
            try:
                # Store in Redis (hot data cache)
                self.cache_user_data(redis_client, event)
                
                # Prepare for OpenSearch bulk insert
                bulk_actions.append({
                    "index": {
                        "_index": "user-events",
                        "_id": event['id']
                    }
                })
                bulk_actions.append(event)
                
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Error processing event {event.get('id')}: {str(e)}")
                continue
        
        # Bulk insert to OpenSearch
        if bulk_actions:
            try:
                response = opensearch_client.bulk(body=bulk_actions)
                if response.get('errors'):
                    logger.warning(f"Some documents failed to index: {response}")
                else:
                    logger.info(f"Successfully indexed {len(bulk_actions)//2} events to OpenSearch")
            except Exception as e:
                logger.error(f"Error bulk indexing events: {str(e)}")
                raise
        
        return processed_count
    
    def process_products(self, products: List[Dict[str, Any]]) -> int:
        """Process product data and store in Redis and OpenSearch"""
        opensearch_client = self.get_opensearch_client()
        redis_client = self.get_redis_client()
        
        processed_count = 0
        bulk_actions = []
        
        for product in products:
            try:
                # Store in Redis (product cache)
                self.cache_product_data(redis_client, product)
                
                # Prepare for OpenSearch bulk insert
                bulk_actions.append({
                    "index": {
                        "_index": "product-catalog",
                        "_id": product['id']
                    }
                })
                bulk_actions.append(product)
                
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Error processing product {product.get('id')}: {str(e)}")
                continue
        
        # Bulk insert to OpenSearch
        if bulk_actions:
            try:
                response = opensearch_client.bulk(body=bulk_actions)
                if response.get('errors'):
                    logger.warning(f"Some products failed to index: {response}")
                else:
                    logger.info(f"Successfully indexed {len(bulk_actions)//2} products to OpenSearch")
            except Exception as e:
                logger.error(f"Error bulk indexing products: {str(e)}")
                raise
        
        return processed_count
    
    def cache_user_data(self, redis_client: redis.Redis, event: Dict[str, Any]):
        """Cache user data in Redis"""
        user_id = event['user_id']
        session_id = event['session_id']
        
        # Cache user session data
        session_key = f"session:{session_id}"
        redis_client.hset(session_key, mapping={
            'user_id': user_id,
            'last_activity': event['timestamp'],
            'last_event': event['event_type'],
            'device_type': event.get('device_type', 'unknown'),
            'location': json.dumps(event.get('location', {}))
        })
        redis_client.expire(session_key, 3600)  # 1 hour TTL
        
        # Cache user activity
        user_key = f"user:{user_id}"
        redis_client.hset(user_key, mapping={
            'last_activity': event['timestamp'],
            'last_event': event['event_type'],
            'current_session': session_id
        })
        redis_client.expire(user_key, 86400)  # 24 hours TTL
        
        # Update event counters
        event_type = event['event_type']
        today = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Daily event counters
        counter_key = f"counters:{today}:{event_type}"
        redis_client.incr(counter_key)
        redis_client.expire(counter_key, 86400 * 7)  # 7 days TTL
        
        # Product popularity counters
        if 'product_id' in event:
            product_key = f"product_popularity:{event['product_id']}"
            redis_client.zincrby('popular_products', 1, event['product_id'])
            redis_client.expire('popular_products', 86400)  # 24 hours TTL
        
        # Search query caching
        if event_type == 'search' and 'search_query' in event:
            search_key = f"search_queries:{today}"
            redis_client.zincrby(search_key, 1, event['search_query'])
            redis_client.expire(search_key, 86400 * 7)  # 7 days TTL
    
    def cache_product_data(self, redis_client: redis.Redis, product: Dict[str, Any]):
        """Cache product data in Redis"""
        product_id = product['id']
        
        # Cache product details
        product_key = f"product:{product_id}"
        redis_client.hset(product_key, mapping={
            'name': product['name'],
            'category': product['category'],
            'price': str(product['price']),
            'brand': product['brand'],
            'rating': str(product.get('rating', 0)),
            'stock_quantity': str(product.get('stock_quantity', 0)),
            'is_active': str(product.get('is_active', True))
        })
        redis_client.expire(product_key, 3600)  # 1 hour TTL
        
        # Update category counters
        category_key = f"category_products:{product['category']}"
        redis_client.sadd(category_key, product_id)
        redis_client.expire(category_key, 86400)  # 24 hours TTL
        
        # Cache for search
        search_key = f"product_search:{product['name'].lower()}"
        redis_client.set(search_key, product_id, ex=3600)  # 1 hour TTL

def lambda_handler(event, context):
    """Lambda handler for data processing"""
    logger.info("Starting data processing")
    
    processor = DataProcessor()
    
    try:
        # Create indices if they don't exist
        processor.create_opensearch_indices()
        
        # Process incoming data
        total_processed = 0
        
        # Handle different event sources
        if 'Records' in event:
            # SQS or SNS event
            for record in event['Records']:
                if 'body' in record:
                    data = json.loads(record['body'])
                else:
                    data = record
                
                total_processed += process_data_batch(processor, data)
        else:
            # Direct invocation
            total_processed += process_data_batch(processor, event)
        
        logger.info(f"Successfully processed {total_processed} records")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Successfully processed {total_processed} records',
                'timestamp': datetime.utcnow().isoformat()
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing data: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
        }

def process_data_batch(processor: DataProcessor, data: Dict[str, Any]) -> int:
    """Process a batch of data"""
    total_processed = 0
    
    # Process events
    if 'events' in data:
        events_processed = processor.process_user_events(data['events'])
        total_processed += events_processed
        logger.info(f"Processed {events_processed} events")
    
    # Process products
    if 'products' in data:
        products_processed = processor.process_products(data['products'])
        total_processed += products_processed
        logger.info(f"Processed {products_processed} products")
    
    # Handle single event
    if 'event_type' in data:
        processor.process_user_events([data])
        total_processed += 1
        logger.info("Processed single event")
    
    return total_processed