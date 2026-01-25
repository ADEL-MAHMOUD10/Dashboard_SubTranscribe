from flask import Blueprint, jsonify, request, url_for, flash, redirect, render_template, session
from module.config import users_collection, csrf, limiter, is_session_valid
import os

billing_bp = Blueprint('billing', __name__)

@billing_bp.route('/pricing')
def pricing():
    """Render pricing page"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    user = users_collection.find_one({'user_id': session['user_id']})
    if not user:
        return redirect(url_for('auth.logout'))
        
    return render_template('pricing.html', credits=user.get('credits', 0), user=user)

@billing_bp.route('/create-payment', methods=['POST'])
@limiter.limit("5 per minute")
def create_payment():
    """Create a PayPal payment order"""
    if 'user_id' not in session or not is_session_valid():
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        package_id = data.get('package_id')
        
        # Define packages
        packages = {
            'mini': {'credits': 25, 'price': 3.00},
            'basic': {'credits': 60, 'price': 5.00},
            'pro': {'credits': 200, 'price': 25.00}, 
            'enterprise': {'credits': 450, 'price': 40.00}
        }
        
        if package_id not in packages:
             return jsonify({'error': 'Invalid package'}), 400
             
        # TODO: Integrate real PayPal SDK here
        # For now, we will return a mock Order ID to simulate the flow
        # In production this would call PayPal API to creating an order
        
        return jsonify({
            'id': 'MOCK_PAYPAL_ORDER_ID_' + package_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@billing_bp.route('/capture-payment', methods=['POST'])
@limiter.limit("5 per minute")
def capture_payment():
    """Capture PayPal payment and update credits"""
    if 'user_id' not in session or not is_session_valid():
        return jsonify({'error': 'Unauthorized'}), 401
        
    try:
        data = request.get_json()
        order_id = data.get('orderID')
        package_id = data.get('package_id') # In real app, get this from order details
        
        # Mock verification
        if 'MOCK' in order_id:
             packages = {
                'mini': 25,
                'basic': 60,
                'pro': 200,
                'enterprise': 450
             }
             credit_amount = packages.get(package_id, 0)
             
             # Add credits to user
             users_collection.update_one(
                 {'user_id': session['user_id']},
                 {'$inc': {'credits': credit_amount}}
             )
             
             return jsonify({'status': 'COMPLETED', 'added_credits': credit_amount})
             
        # TODO: Implement Real Capture Logic
        
        return jsonify({'error': 'Payment failed'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500
