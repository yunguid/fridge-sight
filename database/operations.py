from .models import Session, FridgeEvent, FridgeItem, ItemHistory
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def record_fridge_event(event_type, image_path=None, light_level=None):
    """Record a fridge event (door open/close, detection)"""
    session = Session()
    try:
        event = FridgeEvent(
            event_type=event_type,
            image_path=image_path,
            light_level=light_level
        )
        session.add(event)
        session.commit()
        return event.id
    except Exception as e:
        logger.error(f"Failed to record fridge event: {e}")
        session.rollback()
        raise
    finally:
        session.close()

def update_items(detected_items, event_id):
    """Update fridge inventory based on detected items"""
    session = Session()
    try:
        # Get current inventory
        current_items = {item.name: item for item in session.query(FridgeItem).filter_by(is_present=True).all()}
        
        # Process detected items
        for item_data in detected_items:
            name = item_data['name']
            quantity = item_data.get('quantity', 1)
            confidence = item_data.get('confidence', 0.0)
            
            if name in current_items:
                # Update existing item
                item = current_items[name]
                old_quantity = item.quantity
                item.quantity = quantity
                item.last_seen = datetime.utcnow()
                item.confidence = max(item.confidence, confidence)
                
                # Record history if quantity changed
                if old_quantity != quantity:
                    history = ItemHistory(
                        item_id=item.id,
                        event_id=event_id,
                        action='updated',
                        quantity_change=quantity - old_quantity
                    )
                    session.add(history)
            else:
                # Add new item
                new_item = FridgeItem(
                    name=name,
                    quantity=quantity,
                    confidence=confidence
                )
                session.add(new_item)
                session.flush()  # Get the ID
                
                history = ItemHistory(
                    item_id=new_item.id,
                    event_id=event_id,
                    action='added',
                    quantity_change=quantity
                )
                session.add(history)
        
        session.commit()
    except Exception as e:
        logger.error(f"Failed to update items: {e}")
        session.rollback()
        raise
    finally:
        session.close()

def get_current_inventory():
    """Get current fridge inventory"""
    session = Session()
    try:
        return [
            {
                'name': item.name,
                'quantity': item.quantity,
                'first_seen': item.first_seen,
                'last_seen': item.last_seen,
                'confidence': item.confidence
            }
            for item in session.query(FridgeItem).filter_by(is_present=True).all()
        ]
    finally:
        session.close() 