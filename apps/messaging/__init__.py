"""
Messaging App - Centralized message dispatching system.

This app provides a unified interface for sending messages across multiple channels:
- WhatsApp
- Instagram
- Email

Usage:
    from apps.messaging.dispatcher import MessageDispatcher
    
    dispatcher = MessageDispatcher()
    result = dispatcher.send_message(
        channel='whatsapp',
        recipient='+5511999999999',
        content={'text': 'Hello!'},
        store_id='store-uuid'
    )
"""

default_app_config = 'apps.messaging.apps.MessagingConfig'
