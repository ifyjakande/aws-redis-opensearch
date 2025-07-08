#!/usr/bin/env python3
"""
End-to-End Testing Script for OpenSearch + Redis Pipeline
Tests all components of the data engineering pipeline
"""

import json
import boto3
import requests
import time
import random
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging
from data_generator import DataGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PipelineTester:
    """Test the complete data pipeline"""
    
    def __init__(self, project_name: str = 'opensearch-redis-pipeline', environment: str = 'dev'):
        self.project_name = project_name
        self.environment = environment
        self.lambda_client = boto3.client('lambda')
        self.cloudformation_client = boto3.client('cloudformation')
        self.ssm_client = boto3.client('ssm')
        
        # Get API Gateway URL from CloudFormation exports
        self.api_url = self._get_api_url()
        
        # Initialize data generator
        self.data_generator = DataGenerator()
        
        # Test results
        self.test_results = {
            'start_time': datetime.utcnow().isoformat(),
            'tests': [],
            'summary': {}
        }
    
    def _get_api_url(self) -> Optional[str]:
        """Get API Gateway URL from CloudFormation exports"""
        try:
            response = self.cloudformation_client.list_exports()
            exports = response['Exports']
            
            export_name = f'{self.project_name}-{self.environment}-api-gateway-url'
            for export in exports:
                if export['Name'] == export_name:
                    return export['Value']
            
            logger.warning(f"API Gateway URL export not found: {export_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting API URL: {str(e)}")
            return None
    
    def _get_lambda_function_name(self, function_type: str) -> str:
        """Get Lambda function name"""
        return f'{self.project_name}-{self.environment}-{function_type}'
    
    def _log_test_result(self, test_name: str, success: bool, message: str, details: Dict[str, Any] = None):
        """Log test result"""
        result = {
            'test_name': test_name,
            'success': success,
            'message': message,
            'timestamp': datetime.utcnow().isoformat(),
            'details': details or {}
        }
        
        self.test_results['tests'].append(result)
        
        if success:
            logger.info(f"✅ {test_name}: {message}")
        else:
            logger.error(f"❌ {test_name}: {message}")
    
    def test_infrastructure_health(self) -> bool:
        """Test if infrastructure is healthy"""
        logger.info("Testing infrastructure health...")
        
        success = True
        
        # Test CloudFormation stacks
        stacks = [
            f'{self.project_name}-base',
            f'{self.project_name}-storage',
            f'{self.project_name}-compute',
            f'{self.project_name}-api'
        ]
        
        for stack_name in stacks:
            try:
                response = self.cloudformation_client.describe_stacks(StackName=stack_name)
                stack_status = response['Stacks'][0]['StackStatus']
                
                if stack_status == 'CREATE_COMPLETE' or stack_status == 'UPDATE_COMPLETE':
                    self._log_test_result(
                        f'Stack Health: {stack_name}',
                        True,
                        f'Stack is healthy: {stack_status}'
                    )
                else:
                    self._log_test_result(
                        f'Stack Health: {stack_name}',
                        False,
                        f'Stack is not healthy: {stack_status}'
                    )
                    success = False
                    
            except Exception as e:
                self._log_test_result(
                    f'Stack Health: {stack_name}',
                    False,
                    f'Error checking stack: {str(e)}'
                )
                success = False
        
        return success
    
    def test_lambda_functions(self) -> bool:
        """Test Lambda functions"""
        logger.info("Testing Lambda functions...")
        
        success = True
        functions = ['data-generator', 'data-processor', 'api-handler']
        
        for function_type in functions:
            function_name = self._get_lambda_function_name(function_type)
            
            try:
                # Check if function exists and is active
                response = self.lambda_client.get_function(FunctionName=function_name)
                state = response['Configuration']['State']
                
                if state == 'Active':
                    self._log_test_result(
                        f'Lambda Function: {function_type}',
                        True,
                        f'Function is active',
                        {'function_name': function_name}
                    )
                else:
                    self._log_test_result(
                        f'Lambda Function: {function_type}',
                        False,
                        f'Function is not active: {state}',
                        {'function_name': function_name}
                    )
                    success = False
                    
            except Exception as e:
                self._log_test_result(
                    f'Lambda Function: {function_type}',
                    False,
                    f'Error checking function: {str(e)}',
                    {'function_name': function_name}
                )
                success = False
        
        return success
    
    def test_data_generation(self) -> bool:
        """Test data generation Lambda"""
        logger.info("Testing data generation...")
        
        function_name = self._get_lambda_function_name('data-generator')
        
        try:
            # Invoke data generator
            test_payload = {
                'batch_size': 10,
                'test_mode': True
            }
            
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(test_payload)
            )
            
            if response['StatusCode'] == 200:
                payload = json.loads(response['Payload'].read())
                
                if payload.get('statusCode') == 200:
                    body = json.loads(payload['body'])
                    self._log_test_result(
                        'Data Generation',
                        True,
                        f'Generated data successfully',
                        {'response': body}
                    )
                    return True
                else:
                    self._log_test_result(
                        'Data Generation',
                        False,
                        f'Function returned error: {payload}',
                        {'response': payload}
                    )
                    return False
            else:
                self._log_test_result(
                    'Data Generation',
                    False,
                    f'Lambda invocation failed: {response["StatusCode"]}',
                    {'response': response}
                )
                return False
                
        except Exception as e:
            self._log_test_result(
                'Data Generation',
                False,
                f'Error invoking data generator: {str(e)}'
            )
            return False
    
    def test_data_processing(self) -> bool:
        """Test data processing Lambda"""
        logger.info("Testing data processing...")
        
        function_name = self._get_lambda_function_name('data-processor')
        
        try:
            # Generate test data
            test_data = self.data_generator.generate_batch(5)
            
            # Invoke data processor
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(test_data)
            )
            
            if response['StatusCode'] == 200:
                payload = json.loads(response['Payload'].read())
                
                if payload.get('statusCode') == 200:
                    body = json.loads(payload['body'])
                    self._log_test_result(
                        'Data Processing',
                        True,
                        f'Processed data successfully',
                        {'response': body}
                    )
                    return True
                else:
                    self._log_test_result(
                        'Data Processing',
                        False,
                        f'Function returned error: {payload}',
                        {'response': payload}
                    )
                    return False
            else:
                self._log_test_result(
                    'Data Processing',
                    False,
                    f'Lambda invocation failed: {response["StatusCode"]}',
                    {'response': response}
                )
                return False
                
        except Exception as e:
            self._log_test_result(
                'Data Processing',
                False,
                f'Error invoking data processor: {str(e)}'
            )
            return False
    
    def test_api_endpoints(self) -> bool:
        """Test API Gateway endpoints"""
        logger.info("Testing API endpoints...")
        
        if not self.api_url:
            self._log_test_result(
                'API Endpoints',
                False,
                'API URL not available'
            )
            return False
        
        success = True
        endpoints = [
            ('/health', 'Health Check'),
            ('/metrics', 'Metrics'),
            ('/analytics', 'Analytics'),
            ('/search?q=smartphone', 'Search'),
            ('/cache?pattern=user:*', 'Cache Lookup')
        ]
        
        for endpoint, description in endpoints:
            try:
                url = f"{self.api_url}{endpoint}"
                response = requests.get(url, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    self._log_test_result(
                        f'API Endpoint: {description}',
                        True,
                        f'Endpoint responded successfully',
                        {'url': url, 'response_size': len(str(data))}
                    )
                else:
                    self._log_test_result(
                        f'API Endpoint: {description}',
                        False,
                        f'Endpoint returned status {response.status_code}',
                        {'url': url, 'response': response.text}
                    )
                    success = False
                    
            except Exception as e:
                self._log_test_result(
                    f'API Endpoint: {description}',
                    False,
                    f'Error calling endpoint: {str(e)}',
                    {'url': url}
                )
                success = False
        
        return success
    
    def test_end_to_end_flow(self) -> bool:
        """Test complete end-to-end data flow"""
        logger.info("Testing end-to-end data flow...")
        
        try:
            # Step 1: Generate data
            logger.info("Step 1: Generating test data...")
            test_data = self.data_generator.generate_batch(20)
            
            # Step 2: Process data
            logger.info("Step 2: Processing data...")
            processor_function = self._get_lambda_function_name('data-processor')
            
            response = self.lambda_client.invoke(
                FunctionName=processor_function,
                InvocationType='RequestResponse',
                Payload=json.dumps(test_data)
            )
            
            if response['StatusCode'] != 200:
                self._log_test_result(
                    'End-to-End Flow',
                    False,
                    'Data processing failed'
                )
                return False
            
            # Wait for data to be indexed
            logger.info("Step 3: Waiting for data indexing...")
            time.sleep(10)
            
            # Step 4: Test search functionality
            logger.info("Step 4: Testing search...")
            if not self.api_url:
                self._log_test_result(
                    'End-to-End Flow',
                    False,
                    'API URL not available for search testing'
                )
                return False
            
            search_url = f"{self.api_url}/search?q=*&size=5"
            search_response = requests.get(search_url, timeout=30)
            
            if search_response.status_code != 200:
                self._log_test_result(
                    'End-to-End Flow',
                    False,
                    f'Search endpoint failed: {search_response.status_code}'
                )
                return False
            
            search_data = search_response.json()
            results_count = search_data.get('results', {}).get('total', 0)
            
            # Step 5: Test cache functionality
            logger.info("Step 5: Testing cache...")
            cache_url = f"{self.api_url}/cache?pattern=user:*"
            cache_response = requests.get(cache_url, timeout=30)
            
            if cache_response.status_code != 200:
                self._log_test_result(
                    'End-to-End Flow',
                    False,
                    f'Cache endpoint failed: {cache_response.status_code}'
                )
                return False
            
            cache_data = cache_response.json()
            cache_count = cache_data.get('count', 0)
            
            # Step 6: Test analytics
            logger.info("Step 6: Testing analytics...")
            analytics_url = f"{self.api_url}/analytics"
            analytics_response = requests.get(analytics_url, timeout=30)
            
            if analytics_response.status_code != 200:
                self._log_test_result(
                    'End-to-End Flow',
                    False,
                    f'Analytics endpoint failed: {analytics_response.status_code}'
                )
                return False
            
            analytics_data = analytics_response.json()
            total_events = analytics_data.get('total_events', 0)
            
            # Verify results
            if results_count > 0 and cache_count > 0:
                self._log_test_result(
                    'End-to-End Flow',
                    True,
                    f'Complete flow successful',
                    {
                        'processed_records': test_data['total_records'],
                        'search_results': results_count,
                        'cache_entries': cache_count,
                        'total_events': total_events
                    }
                )
                return True
            else:
                self._log_test_result(
                    'End-to-End Flow',
                    False,
                    f'Data flow incomplete',
                    {
                        'search_results': results_count,
                        'cache_entries': cache_count
                    }
                )
                return False
                
        except Exception as e:
            self._log_test_result(
                'End-to-End Flow',
                False,
                f'Error in end-to-end test: {str(e)}'
            )
            return False
    
    def test_performance(self) -> bool:
        """Test system performance"""
        logger.info("Testing system performance...")
        
        if not self.api_url:
            self._log_test_result(
                'Performance Test',
                False,
                'API URL not available'
            )
            return False
        
        try:
            # Test API response times
            endpoints = ['/health', '/metrics', '/search?q=*', '/analytics']
            response_times = []
            
            for endpoint in endpoints:
                url = f"{self.api_url}{endpoint}"
                start_time = time.time()
                
                response = requests.get(url, timeout=30)
                end_time = time.time()
                
                response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                response_times.append(response_time)
                
                if response.status_code == 200:
                    logger.info(f"Endpoint {endpoint}: {response_time:.2f}ms")
                else:
                    logger.warning(f"Endpoint {endpoint} failed: {response.status_code}")
            
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            
            # Performance criteria
            success = avg_response_time < 1000 and max_response_time < 2000  # 1s avg, 2s max
            
            self._log_test_result(
                'Performance Test',
                success,
                f'Average response time: {avg_response_time:.2f}ms, Max: {max_response_time:.2f}ms',
                {
                    'avg_response_time_ms': avg_response_time,
                    'max_response_time_ms': max_response_time,
                    'response_times': response_times
                }
            )
            
            return success
            
        except Exception as e:
            self._log_test_result(
                'Performance Test',
                False,
                f'Error in performance test: {str(e)}'
            )
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return results"""
        logger.info("Starting comprehensive pipeline testing...")
        logger.info("=" * 60)
        
        tests = [
            ('Infrastructure Health', self.test_infrastructure_health),
            ('Lambda Functions', self.test_lambda_functions),
            ('Data Generation', self.test_data_generation),
            ('Data Processing', self.test_data_processing),
            ('API Endpoints', self.test_api_endpoints),
            ('End-to-End Flow', self.test_end_to_end_flow),
            ('Performance', self.test_performance)
        ]
        
        for test_name, test_function in tests:
            logger.info(f"\n{'='*20} {test_name} {'='*20}")
            try:
                test_function()
            except Exception as e:
                self._log_test_result(
                    test_name,
                    False,
                    f'Test failed with exception: {str(e)}'
                )
        
        # Generate summary
        total_tests = len(self.test_results['tests'])
        passed_tests = sum(1 for test in self.test_results['tests'] if test['success'])
        failed_tests = total_tests - passed_tests
        
        self.test_results['summary'] = {
            'total_tests': total_tests,
            'passed': passed_tests,
            'failed': failed_tests,
            'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            'end_time': datetime.utcnow().isoformat()
        }
        
        # Print summary
        logger.info("\n" + "="*60)
        logger.info("TEST SUMMARY")
        logger.info("="*60)
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests}")
        logger.info(f"Failed: {failed_tests}")
        logger.info(f"Success Rate: {self.test_results['summary']['success_rate']:.1f}%")
        
        if failed_tests > 0:
            logger.info("\nFAILED TESTS:")
            for test in self.test_results['tests']:
                if not test['success']:
                    logger.info(f"  ❌ {test['test_name']}: {test['message']}")
        
        return self.test_results
    
    def save_results(self, filename: str = None):
        """Save test results to file"""
        if not filename:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f'test_results_{timestamp}.json'
        
        with open(filename, 'w') as f:
            json.dump(self.test_results, f, indent=2)
        
        logger.info(f"Test results saved to: {filename}")

def main():
    """Main function for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test OpenSearch + Redis Pipeline')
    parser.add_argument('--project-name', default='opensearch-redis-pipeline',
                       help='Project name (default: opensearch-redis-pipeline)')
    parser.add_argument('--environment', default='dev',
                       help='Environment (default: dev)')
    parser.add_argument('--save-results', action='store_true',
                       help='Save test results to file')
    parser.add_argument('--output-file', help='Output file for test results')
    
    args = parser.parse_args()
    
    # Run tests
    tester = PipelineTester(args.project_name, args.environment)
    results = tester.run_all_tests()
    
    # Save results if requested
    if args.save_results:
        tester.save_results(args.output_file)
    
    # Exit with appropriate code
    success_rate = results['summary']['success_rate']
    exit_code = 0 if success_rate == 100 else 1
    exit(exit_code)

if __name__ == "__main__":
    main()