from django.db import models

class MaintenanceLog(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    work_order_id = models.IntegerField()
    v_idle = models.CharField(max_length=10)
    v_active = models.CharField(max_length=10)
    signal_registered = models.BooleanField()
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)