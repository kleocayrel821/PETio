"""
One-time migration to fix FeedingLog records with incorrect device_id='feeder-1'
that should be associated with the actual Hardware device_id.

Run this manually in Django shell:
python manage.py shell -c "exec(open('controller/migrations/fix_feeding_log_device_id.py').read())"
"""

from controller.models import FeedingLog, Hardware

def migrate_feeding_logs_device_id():
    """Migrate logs with device_id='feeder-1' to actual Hardware device_id"""
    
    # Find all hardware devices that are paired
    paired_hardware = Hardware.objects.filter(is_paired=True)
    
    if not paired_hardware.exists():
        print("No paired hardware devices found. Skipping migration.")
        return
    
    # Use the first paired hardware device as the target
    target_hardware = paired_hardware.first()
    target_device_id = target_hardware.device_id
    
    print(f"Found paired hardware: {target_hardware} with device_id: {target_device_id}")
    
    # Find all logs with the wrong device_id
    wrong_logs = FeedingLog.objects.filter(device_id='feeder-1')
    count = wrong_logs.count()
    
    if count == 0:
        print("No logs found with device_id='feeder-1'. Migration not needed.")
        return
    
    print(f"Found {count} logs with device_id='feeder-1' to migrate.")
    
    # Update the logs
    updated = wrong_logs.update(device_id=target_device_id)
    
    print(f"Successfully migrated {updated} logs to device_id='{target_device_id}'")
    
    # Verify the migration
    remaining_wrong = FeedingLog.objects.filter(device_id='feeder-1').count()
    correct_logs = FeedingLog.objects.filter(device_id=target_device_id).count()
    
    print(f"Remaining logs with device_id='feeder-1': {remaining_wrong}")
    print(f"Total logs with device_id='{target_device_id}': {correct_logs}")

if __name__ == "__main__":
    migrate_feeding_logs_device_id()