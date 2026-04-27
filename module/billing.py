from flask import Blueprint, jsonify, request, url_for, flash, redirect, render_template, session, g
from module.config import users_collection, csrf, limiter, is_session_valid, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_MODE
import os
import requests
import base64
import uuid

billing_bp = Blueprint('billing', __name__)

def get_paypal_base_url():
    if PAYPAL_MODE == 'live':
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"

def get_paypal_access_token():
    try:
        url = f"{get_paypal_base_url()}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US"
        }
        data = {
            "grant_type": "client_credentials"
        }
        
        response = requests.post(
            url, 
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET), 
            headers=headers, 
            data=data
        )
        
        if response.status_code == 200:
            return response.json()['access_token']
        return None
    except Exception as e:
        print(f"PayPal Token Error: {e}")
        return None

@billing_bp.route('/pricing')
def pricing():
    """Render pricing page"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    user = users_collection.find_one({'user_id': session['user_id']})
    if not user:
        return redirect(url_for('auth.logout'))
        
    return render_template('pricing.html', credits=user.get('credits', 0), user=user, paypal_client_id=PAYPAL_CLIENT_ID, paypal_mode=PAYPAL_MODE, nonce=g.nonce)

@billing_bp.route('/create-payment', methods=['POST'])
@limiter.limit("5 per minute")
def create_payment():
    """Create a PayPal payment order"""
    if 'user_id' not in session or not is_session_valid():
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        package_id = data.get('package_id')
        
        packages = {
            'mini': {'credits': 25, 'price': 3.00},
            'basic': {'credits': 60, 'price': 5.00},
            'pro': {'credits': 200, 'price': 25.00}, 
            'enterprise': {'credits': 450, 'price': 40.00}
        }
        
        if package_id not in packages:
             return jsonify({'error': 'Invalid package'}), 400
             
        pkg = packages[package_id]
        
        # MOCK MODE 
        if PAYPAL_MODE == 'mock':
             return jsonify({
                'id': f'MOCK_ORDER_{uuid.uuid4().hex[:12].upper()}_{package_id}',
                'status': 'CREATED'
             })

        access_token = get_paypal_access_token()
        
        if not access_token:
            return jsonify({'error': 'Payment service unavailable'}), 503

        url = f"{get_paypal_base_url()}/v2/checkout/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        payload = {
            "intent": "CAPTURE",
            "application_context": {
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
                "brand_name": "SubTranscribe",
                "return_url": url_for('billing.pricing', _external=True),
                "cancel_url": url_for('billing.pricing', _external=True)
            },
            "purchase_units": [
                {
                    "reference_id": package_id,
                    "description": "Digital Service",
                    "amount": {
                        "currency_code": "USD",
                        "value": f"{pkg['price']:.2f}",
                        "breakdown": {
                            "item_total": {
                                "currency_code": "USD",
                                "value": f"{pkg['price']:.2f}"
                            }
                        }
                    },
                    "items": [
                        {
                            "name": f"{package_id.title()} Credits",
                            "unit_amount": {
                                "currency_code": "USD",
                                "value": f"{pkg['price']:.2f}"
                            },
                            "quantity": "1",
                            "category": "DIGITAL_GOODS"
                        }
                    ]
                }
            ]
        }
        
        # print(f"DEBUG: JSON Payload: {payload}")
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            return jsonify(response.json())
        else:
            print(f"PayPal Create Order Error: {response.text}")
            return jsonify({'error': 'Failed to create order'}), 400
        
    except Exception as e:
        print(f"Create Payment Error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@billing_bp.route('/capture-payment', methods=['POST'])
@limiter.limit("5 per minute")
def capture_payment():
    """Capture PayPal payment and update credits"""
    if 'user_id' not in session or not is_session_valid():
        return jsonify({'error': 'Unauthorized'}), 401
        
    try:
        data = request.get_json()
        order_id = data.get('orderID')
        
        packages = {
            'mini': {'credits': 25, 'price': 3.00},
            'basic': {'credits': 60, 'price': 5.00},
            'pro': {'credits': 200, 'price': 25.00}, 
            'enterprise': {'credits': 450, 'price': 40.00}
        }
        
        package_id = data.get('package_id')
        
        # MOCK MODE
        if PAYPAL_MODE == 'mock':
            if package_id in packages:
                credits = packages[package_id]['credits']
                users_collection.update_one(
                    {'user_id': session['user_id']},
                    {'$inc': {'credits': credits}}
                )
                return jsonify({'status': 'COMPLETED', 'added_credits': credits})
            return jsonify({'error': 'Invalid mock package'}), 400

        access_token = get_paypal_access_token()
        if not access_token:
             return jsonify({'error': 'Payment service unavailable'}), 503

        url = f"{get_paypal_base_url()}/v2/checkout/orders/{order_id}/capture"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        response = requests.post(url, headers=headers)
        
        if response.status_code in [200, 201]:
            capture_data = response.json()
            
            # Verify status
            if capture_data['status'] == 'COMPLETED':
                
                if package_id in packages:
                    credits = packages[package_id]['credits']
                    
                    # Add credits to user
                    users_collection.update_one(
                        {'user_id': session['user_id']},
                        {'$inc': {'credits': credits}}
                    )
                    
                    return jsonify({'status': 'COMPLETED', 'added_credits': credits})
            
            return jsonify({'error': 'Payment not completed', 'details': capture_data}), 400
            
        else:
            print(f"PayPal Capture Error: {response.text}")
            error_data = response.json() if response.content else {}
            error_msg = 'Failed to capture payment'
            
            # Extract detailed message if available
            if 'details' in error_data and error_data['details']:
                issue = error_data['details'][0].get('issue', 'Unknown Issue')
                error_msg += f": {issue}"
                if issue == 'COMPLIANCE_VIOLATION':
                    error_msg += ". Please refer to your Sandbox Account status. Use a different Personal Sandbox Account."
                    
            elif 'message' in error_data:
                error_msg += f": {error_data.get('message')}"
                
            return jsonify({'error': error_msg, 'debug': error_data}), 400

    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
