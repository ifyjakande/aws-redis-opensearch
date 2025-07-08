#!/usr/bin/env python3
"""
API Handler Lambda Function
Provides REST API endpoints for accessing cached and search data
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

class APIHandler:
    """Handle API requests for data access"""
    
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
                # Get OpenSearch endpoint
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
                    timeout=30,
                    max_retries=2,
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
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
                
                # Test connection
                self.redis_client.ping()
                logger.info(f"Redis client initialized for endpoint: {endpoint}:{port}")
                
            except Exception as e:
                logger.error(f"Error initializing Redis client: {str(e)}")
                raise
                
        return self.redis_client

def lambda_handler(event, context):
    """Lambda handler for API requests"""
    logger.info(f"Processing API request: {event.get('httpMethod')} {event.get('path')}")
    
    api_handler = APIHandler()
    
    try:
        # Get HTTP method and path
        method = event.get('httpMethod', 'GET')
        path = event.get('path', '/')
        query_params = event.get('queryStringParameters') or {}
        
        # Route requests
        if path == '/search' and method == 'GET':
            return handle_search(api_handler, query_params)
        elif path == '/cache' and method == 'GET':
            return handle_cache_lookup(api_handler, query_params)
        elif path == '/user' and method == 'GET':
            return handle_user_lookup(api_handler, query_params)
        elif path == '/analytics' and method == 'GET':
            return handle_analytics(api_handler, query_params)
        elif path == '/health' and method == 'GET':
            return handle_health_check(api_handler)
        elif path == '/metrics' and method == 'GET':
            return handle_metrics(api_handler, query_params)
        else:
            return create_response(404, {'error': 'Not Found', 'path': path, 'method': method})
            
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        return create_response(500, {'error': str(e), 'timestamp': datetime.utcnow().isoformat()})

def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(body)
    }

def handle_search(api_handler: APIHandler, query_params: Dict[str, str]) -> Dict[str, Any]:
    """Handle search requests"""
    opensearch_client = api_handler.get_opensearch_client()
    redis_client = api_handler.get_redis_client()
    
    query = query_params.get('q', '*')
    index = query_params.get('index', 'user-events')
    size = min(int(query_params.get('size', 10)), 100)  # Max 100 results
    
    # Check cache first
    cache_key = f"search_cache:{index}:{query}:{size}"
    try:
        cached_result = redis_client.get(cache_key)
        if cached_result:
            logger.info(f"Returning cached search result for query: {query}")
            return create_response(200, {
                'query': query,
                'index': index,
                'cached': True,
                'results': json.loads(cached_result)
            })
    except Exception as e:
        logger.warning(f"Cache lookup failed: {str(e)}")
    
    try:
        # Build OpenSearch query
        if query == '*':
            search_body = {
                "query": {"match_all": {}},
                "size": size,
                "sort": [{"timestamp": {"order": "desc"}}]
            }
        else:
            search_body = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["name^2", "description", "category", "search_query", "event_type"],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                },
                "size": size,
                "sort": [{"_score": {"order": "desc"}}, {"timestamp": {"order": "desc"}}]
            }
        
        # Execute search
        response = opensearch_client.search(index=index, body=search_body)
        
        # Format results
        results = {
            'hits': [hit['_source'] for hit in response['hits']['hits']],
            'total': response['hits']['total']['value'] if isinstance(response['hits']['total'], dict) else response['hits']['total'],
            'max_score': response['hits']['max_score']
        }
        
        # Cache result for 5 minutes
        try:
            redis_client.setex(cache_key, 300, json.dumps(results))
        except Exception as e:
            logger.warning(f"Failed to cache search result: {str(e)}")
        
        logger.info(f"Search completed: {results['total']} results for query '{query}'")
        
        return create_response(200, {
            'query': query,
            'index': index,
            'cached': False,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return create_response(500, {'error': f'Search failed: {str(e)}'})

def handle_cache_lookup(api_handler: APIHandler, query_params: Dict[str, str]) -> Dict[str, Any]:
    """Handle cache lookup requests"""
    redis_client = api_handler.get_redis_client()
    
    key = query_params.get('key')
    pattern = query_params.get('pattern')
    
    if not key and not pattern:
        return create_response(400, {'error': 'Either key or pattern parameter is required'})
    
    try:
        if key:
            # Direct key lookup
            if redis_client.exists(key):
                key_type = redis_client.type(key)
                
                if key_type == 'string':
                    value = redis_client.get(key)
                elif key_type == 'hash':
                    value = redis_client.hgetall(key)
                elif key_type == 'set':
                    value = list(redis_client.smembers(key))
                elif key_type == 'zset':
                    value = redis_client.zrange(key, 0, -1, withscores=True)
                elif key_type == 'list':
                    value = redis_client.lrange(key, 0, -1)
                else:
                    value = f"Unsupported type: {key_type}"
                
                ttl = redis_client.ttl(key)
                
                return create_response(200, {
                    'key': key,
                    'type': key_type,
                    'value': value,
                    'ttl': ttl
                })
            else:
                return create_response(404, {'error': f'Key not found: {key}'})
        
        elif pattern:
            # Pattern search
            keys = redis_client.keys(pattern)
            if len(keys) > 100:  # Limit results
                keys = keys[:100]
                
            results = {}
            for k in keys:
                try:
                    key_type = redis_client.type(k)
                    if key_type == 'string':
                        results[k] = redis_client.get(k)
                    elif key_type == 'hash':
                        results[k] = redis_client.hgetall(k)
                    # Add other types as needed
                except Exception as e:
                    results[k] = f"Error: {str(e)}"
            
            return create_response(200, {
                'pattern': pattern,
                'count': len(results),
                'results': results
            })
        
    except Exception as e:
        logger.error(f"Cache lookup error: {str(e)}")
        return create_response(500, {'error': f'Cache lookup failed: {str(e)}'})

def handle_user_lookup(api_handler: APIHandler, query_params: Dict[str, str]) -> Dict[str, Any]:
    """Handle user data lookup"""
    redis_client = api_handler.get_redis_client()
    
    user_id = query_params.get('user_id')
    if not user_id:
        return create_response(400, {'error': 'user_id parameter is required'})
    
    try:
        # Get user data from cache
        user_key = f"user:{user_id}"
        user_data = redis_client.hgetall(user_key)
        
        if not user_data:
            return create_response(404, {'error': f'User not found: {user_id}'})
        
        # Get current session data if available
        session_data = {}
        if 'current_session' in user_data:
            session_key = f"session:{user_data['current_session']}"
            session_data = redis_client.hgetall(session_key)
        
        return create_response(200, {
            'user_id': user_id,
            'user_data': user_data,
            'session_data': session_data
        })
        
    except Exception as e:
        logger.error(f"User lookup error: {str(e)}")
        return create_response(500, {'error': f'User lookup failed: {str(e)}'})

def handle_analytics(api_handler: APIHandler, query_params: Dict[str, str]) -> Dict[str, Any]:
    """Handle analytics requests"""
    redis_client = api_handler.get_redis_client()
    
    try:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Get popular products
        popular_products = redis_client.zrevrange('popular_products', 0, 9, withscores=True)
        
        # Get search queries
        search_queries_key = f"search_queries:{today}"
        popular_searches = redis_client.zrevrange(search_queries_key, 0, 9, withscores=True)
        
        # Get event counters
        event_types = ['view', 'click', 'purchase', 'search', 'add_to_cart']
        event_counts = {}
        for event_type in event_types:
            counter_key = f"counters:{today}:{event_type}"
            count = redis_client.get(counter_key) or 0
            event_counts[event_type] = int(count)
        
        return create_response(200, {
            'date': today,
            'popular_products': [{'product_id': p[0], 'score': p[1]} for p in popular_products],
            'popular_searches': [{'query': s[0], 'count': s[1]} for s in popular_searches],
            'event_counts': event_counts,
            'total_events': sum(event_counts.values())
        })
        
    except Exception as e:
        logger.error(f"Analytics error: {str(e)}")
        return create_response(500, {'error': f'Analytics failed: {str(e)}'})

def handle_metrics(api_handler: APIHandler, query_params: Dict[str, str]) -> Dict[str, Any]:
    """Handle system metrics requests"""
    redis_client = api_handler.get_redis_client()
    
    try:
        # Redis info
        redis_info = redis_client.info()
        
        # Key statistics
        total_keys = len(redis_client.keys('*'))
        
        metrics = {
            'redis': {
                'connected_clients': redis_info.get('connected_clients', 0),
                'used_memory': redis_info.get('used_memory', 0),
                'used_memory_human': redis_info.get('used_memory_human', '0B'),
                'total_commands_processed': redis_info.get('total_commands_processed', 0),
                'total_keys': total_keys
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return create_response(200, metrics)
        
    except Exception as e:
        logger.error(f"Metrics error: {str(e)}")
        return create_response(500, {'error': f'Metrics failed: {str(e)}'})

def handle_health_check(api_handler: APIHandler) -> Dict[str, Any]:
    """Handle health check requests"""
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'services': {}
    }
    
    # Check Redis
    try:
        redis_client = api_handler.get_redis_client()
        redis_client.ping()
        health_status['services']['redis'] = 'healthy'
    except Exception as e:
        health_status['services']['redis'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'degraded'
    
    # Check OpenSearch
    try:
        opensearch_client = api_handler.get_opensearch_client()
        opensearch_client.cluster.health()
        health_status['services']['opensearch'] = 'healthy'
    except Exception as e:
        health_status['services']['opensearch'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'degraded'
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return create_response(status_code, health_status)