#!/usr/bin/env python
# Quick migration script to fix feeding log device_id

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
sys.path.append('D:\\PETio')
django.setup()

from controller.models import FeedingLog, Hardware

def run_migration():
    print("Starting feeding log device_id migration...")
    
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
    print("Migration completed successfully!")

if __name__ == "__main__":
    run_migration()