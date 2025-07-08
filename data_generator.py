#!/usr/bin/env python3
"""
Data generator for OpenSearch + Redis pipeline
"""

import json
import random
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
import boto3
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataGenerator:
    """E-commerce data generator"""
    
    def __init__(self):
        self.categories = [
            'electronics', 'clothing', 'books', 'home', 'sports', 
            'beauty', 'toys', 'automotive', 'health', 'food'
        ]
        
        self.event_types = [
            'view', 'click', 'add_to_cart', 'purchase', 'search', 
            'wishlist', 'review', 'share', 'compare', 'checkout'
        ]
        
        self.product_names = [
            'smartphone', 'laptop', 'headphones', 'shoes', 'book', 
            'watch', 'camera', 'tablet', 'speaker', 'backpack',
            'keyboard', 'monitor', 'mouse', 'charger', 'case'
        ]
        
        self.search_queries = [
            'best smartphone 2024', 'wireless headphones', 'gaming laptop',
            'running shoes', 'python programming', 'smartwatch fitness',
            'bluetooth speaker', 'travel backpack', 'mechanical keyboard',
            'ultrawide monitor', 'wireless mouse', 'phone case', 'book mystery'
        ]
        
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        ]
        
        self.locations = [
            {'city': 'New York', 'state': 'NY', 'country': 'US'},
            {'city': 'Los Angeles', 'state': 'CA', 'country': 'US'},
            {'city': 'Chicago', 'state': 'IL', 'country': 'US'},
            {'city': 'Houston', 'state': 'TX', 'country': 'US'},
            {'city': 'Phoenix', 'state': 'AZ', 'country': 'US'},
        ]

    def generate_user_event(self, user_id: str = None, session_id: str = None) -> Dict[str, Any]:
        """Generate user event record"""
        if not user_id:
            user_id = f'user_{random.randint(1, 1000)}'
        
        if not session_id:
            session_id = f'session_{random.randint(1, 500)}'
            
        event_type = random.choice(self.event_types)
        location = random.choice(self.locations)
        
        # Generate timestamp within last 24 hours
        now = datetime.utcnow()
        timestamp = now - timedelta(seconds=random.randint(0, 86400))
        
        event = {
            'id': str(uuid.uuid4()),
            'user_id': user_id,
            'session_id': session_id,
            'timestamp': timestamp.isoformat() + 'Z',
            'event_type': event_type,
            'product_id': f'product_{random.randint(1, 1000)}',
            'category': random.choice(self.categories),
            'price': round(random.uniform(5.99, 999.99), 2),
            'quantity': random.randint(1, 10) if event_type in ['add_to_cart', 'purchase'] else 1,
            'currency': 'USD',
            'user_agent': random.choice(self.user_agents),
            'ip_address': f'{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}',
            'location': location,
            'device_type': random.choice(['desktop', 'mobile', 'tablet']),
            'referrer': random.choice(['google.com', 'facebook.com', 'direct', 'email', 'twitter.com']),
            'page_url': f'/products/{random.choice(self.product_names)}',
            'revenue': round(random.uniform(5.99, 999.99), 2) if event_type == 'purchase' else 0
        }
        
        # Add event-specific fields
        if event_type == 'search':
            event['search_query'] = random.choice(self.search_queries)
            event['search_results_count'] = random.randint(0, 1000)
            
        elif event_type == 'review':
            event['rating'] = random.randint(1, 5)
            event['review_text'] = f'Great product! Rating: {event["rating"]}/5'
            
        elif event_type == 'purchase':
            event['payment_method'] = random.choice(['credit_card', 'paypal', 'apple_pay', 'google_pay'])
            event['discount_applied'] = random.choice([True, False])
            if event['discount_applied']:
                event['discount_amount'] = round(event['price'] * 0.1, 2)
                
        return event

    def generate_product_data(self, product_id: str = None) -> Dict[str, Any]:
        """Generate product record"""
        if not product_id:
            product_id = f'product_{random.randint(1, 1000)}'
            
        product_name = random.choice(self.product_names)
        category = random.choice(self.categories)
        
        product = {
            'id': product_id,
            'name': f'{product_name.title()} {random.randint(1, 100)}',
            'category': category,
            'subcategory': f'{category}_sub_{random.randint(1, 5)}',
            'price': round(random.uniform(5.99, 999.99), 2),
            'currency': 'USD',
            'brand': f'Brand_{random.randint(1, 50)}',
            'description': f'High-quality {product_name} with excellent features',
            'tags': [product_name, category, 'bestseller', 'new'],
            'stock_quantity': random.randint(0, 1000),
            'weight': round(random.uniform(0.1, 10.0), 2),
            'dimensions': {
                'length': round(random.uniform(1, 50), 2),
                'width': round(random.uniform(1, 50), 2),
                'height': round(random.uniform(1, 50), 2)
            },
            'rating': round(random.uniform(1, 5), 1),
            'review_count': random.randint(0, 1000),
            'created_at': (datetime.utcnow() - timedelta(days=random.randint(1, 365))).isoformat() + 'Z',
            'updated_at': datetime.utcnow().isoformat() + 'Z',
            'is_active': True,
            'image_url': f'https://example.com/images/{product_id}.jpg'
        }
        
        return product

    def generate_user_session(self, user_id: str = None, session_duration_minutes: int = 30) -> List[Dict[str, Any]]:
        """Generate user session with multiple events"""
        if not user_id:
            user_id = f'user_{random.randint(1, 1000)}'
            
        session_id = f'session_{uuid.uuid4().hex[:8]}'
        session_start = datetime.utcnow() - timedelta(minutes=random.randint(1, 1440))
        
        # Generate 1-10 events for this session
        num_events = random.randint(1, 10)
        events = []
        
        for i in range(num_events):
            event = self.generate_user_event(user_id, session_id)
            # Adjust timestamp to be within session duration
            event_time = session_start + timedelta(minutes=random.randint(0, session_duration_minutes))
            event['timestamp'] = event_time.isoformat() + 'Z'
            events.append(event)
            
        return events

    def generate_batch(self, batch_size: int = 100) -> Dict[str, Any]:
        """Generate batch of events and products"""
        events = []
        products = []
        
        # Generate user events (70% of batch)
        events_count = int(batch_size * 0.7)
        for _ in range(events_count):
            events.append(self.generate_user_event())
            
        # Generate product data (30% of batch)
        products_count = batch_size - events_count
        for _ in range(products_count):
            products.append(self.generate_product_data())
            
        return {
            'events': events,
            'products': products,
            'batch_id': str(uuid.uuid4()),
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'total_records': len(events) + len(products)
        }

    def generate_and_save_to_file(self, filename: str, batch_size: int = 100):
        """Generate and save to file"""
        data = self.generate_batch(batch_size)
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        logger.info(f"Generated {data['total_records']} records and saved to {filename}")
        return data

    def send_to_lambda(self, lambda_function_name: str, data: Dict[str, Any]):
        """Send data to Lambda function"""
        lambda_client = boto3.client('lambda')
        
        try:
            response = lambda_client.invoke(
                FunctionName=lambda_function_name,
                InvocationType='Event',  # Asynchronous
                Payload=json.dumps(data)
            )
            
            logger.info(f"Sent data to Lambda function {lambda_function_name}")
            return response
            
        except Exception as e:
            logger.error(f"Error sending data to Lambda: {str(e)}")
            raise

    def send_to_api(self, api_endpoint: str, data: Dict[str, Any]):
        """Send data to API endpoint"""
        try:
            response = requests.post(
                api_endpoint,
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            response.raise_for_status()
            logger.info(f"Sent data to API endpoint {api_endpoint}")
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending data to API: {str(e)}")
            raise

def lambda_handler(event, context):
    """Lambda handler for data generation"""
    generator = DataGenerator()
    
    # Get batch size from event or use default
    batch_size = event.get('batch_size', 100)
    
    # Generate data
    data = generator.generate_batch(batch_size)
    
    # If processor function is specified, send data there
    if 'processor_function' in event:
        generator.send_to_lambda(event['processor_function'], data)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'Generated {data["total_records"]} records',
            'batch_id': data['batch_id'],
            'generated_at': data['generated_at']
        })
    }

def main():
    """Command-line interface"""
    generator = DataGenerator()
    
    print("Data Generator for OpenSearch + Redis Pipeline")
    print("=" * 50)
    
    while True:
        print("\nOptions:")
        print("1. Generate single event")
        print("2. Generate user session")
        print("3. Generate product data")
        print("4. Generate batch and save to file")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == '1':
            event = generator.generate_user_event()
            print(json.dumps(event, indent=2))
            
        elif choice == '2':
            events = generator.generate_user_session()
            print(f"Generated {len(events)} events for session:")
            for event in events:
                print(json.dumps(event, indent=2))
                
        elif choice == '3':
            product = generator.generate_product_data()
            print(json.dumps(product, indent=2))
            
        elif choice == '4':
            batch_size = int(input("Enter batch size (default 100): ") or "100")
            filename = input("Enter filename (default: sample_data.json): ") or "sample_data.json"
            generator.generate_and_save_to_file(filename, batch_size)
            
        elif choice == '5':
            print("Exiting...")
            break
            
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()