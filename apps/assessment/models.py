from django.db import models

class WorkOrder(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    # Storing the logic as JSON makes it easy to parse in JS
    broken_logic = models.JSONField(help_text="The initial faulty logic state")
    target_logic = models.JSONField(help_text="The correct logic state")
    difficulty = models.IntegerField(default=1)

    def __str__(self):
        return self.title