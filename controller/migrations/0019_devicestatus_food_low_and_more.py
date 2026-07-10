from django.db import migrations, models

class Migration(migrations.Migration):

dependencies = [

("controller", "0018_update_portion_size_wheel_30g"),

]

operations = [

migrations.AddField(

model_name="devicestatus",

name="hopper_distance_mm",

field=models.IntegerField(blank=True, null=True),

),

migrations.AddField(

model_name="devicestatus",

name="hopper_level_pct",

field=models.IntegerField(blank=True, null=True),

),

migrations.AddField(

model_name="devicestatus",

name="food_low",

field=models.BooleanField(default=False),

),

migrations.AddField(

model_name="devicestatus",

name="tof_ok",

field=models.BooleanField(default=False),

),

]

